"""Day07: fixed-route multi-hop DCF and metric collection.

This module extends the actual Day06 DCFContentionMac implementation without
modifying Day03-Day06 files. It adds:

1. fixed-route hop-by-hop forwarding;
2. relay re-enqueue and a fresh DCF contention cycle at every hop;
3. per-hop and end-to-end DCF metrics;
4. compatibility with Day06 collision, ACK timeout, BEB, and retry behavior.

The protocol remains ordinary DCF/CSMA-CA. No path reservation or RL is used.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
DAY05_CODE = DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
DAY06_CODE = DAILY_DIR / "Day06_DCF碰撞与重传" / "code"

for path in (CURRENT_DIR, DAY03_CODE, DAY04_CODE, DAY05_CODE, DAY06_CODE):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from metrics import MetricsCollector  # type: ignore  # noqa: E402
from node import MacState, Node  # type: ignore  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from dcf_collision_mac import (  # type: ignore  # noqa: E402
    CollisionChannel,
    DCFContentionCoordinator,
    DCFContentionMac,
    SequenceRandom,
)


@dataclass(slots=True)
class HopMetrics:
    """Metrics for one successfully completed DCF hop."""

    packet_id: int
    hop_index: int
    sender: int
    receiver: int
    queue_enter_at: float
    first_difs_start_at: float
    successful_tx_start_at: float
    ack_at: float
    queue_delay: float
    access_delay: float
    tx_ack_delay: float
    hop_delay: float
    difs_starts: int
    competition_attempts: int
    selected_backoff_slots: int
    consumed_backoff_slots: int
    backoff_freezes: int
    retries: int


@dataclass(slots=True)
class _HopContext:
    """Mutable event context while one packet is contending for one hop."""

    packet_id: int
    hop_index: int
    node_id: int
    queue_enter_at: float
    first_difs_start_at: float | None = None
    last_tx_start_at: float | None = None
    difs_starts: int = 0
    competition_attempts: int = 0
    selected_backoff_slots: int = 0
    consumed_backoff_slots: int = 0
    backoff_freezes: int = 0


class DCFMetricsCollector(MetricsCollector):
    """Day03 collector plus DCF-specific counters and per-hop records."""

    _SLOTS_PATTERN = re.compile(r"(?:^|,\s*)slots=(\d+)")

    def __init__(self, *, slot_time: float) -> None:
        super().__init__()
        if slot_time <= 0:
            raise ValueError("slot_time must be positive.")

        self.slot_time = float(slot_time)
        self.difs_starts = 0
        self.competition_attempts = 0
        self.backoff_starts = 0
        self.backoff_resumes = 0
        self.backoff_freezes = 0
        self.selected_backoff_slots = 0
        self.consumed_backoff_slots = 0
        self.ack_timeouts = 0
        self.collided_packet_attempts = 0
        self.shared_collision_events = 0
        self.successful_hops = 0
        self.dropped_hops = 0

        self.hop_records: list[HopMetrics] = []
        self._hop_contexts: dict[tuple[int, int], _HopContext] = {}
        self.packet_retry_counts: dict[int, int] = defaultdict(int)
        self.packet_competition_counts: dict[int, int] = defaultdict(int)
        self.packet_difs_counts: dict[int, int] = defaultdict(int)

    @staticmethod
    def _key(packet: Packet) -> tuple[int, int]:
        return int(packet.packet_id), int(packet.current_hop_index)

    def record_queue_entry(self, packet: Packet, *, node_id: int, at: float) -> None:
        """Open one hop context when a source or relay packet enters a queue."""
        key = self._key(packet)
        if key in self._hop_contexts:
            raise RuntimeError(
                f"Duplicate queue-entry context for packet={packet.packet_id}, "
                f"hop={packet.current_hop_index}."
            )
        self._hop_contexts[key] = _HopContext(
            packet_id=int(packet.packet_id),
            hop_index=int(packet.current_hop_index),
            node_id=int(node_id),
            queue_enter_at=float(at),
        )

    def observe_mac_event(
        self,
        *,
        time: float,
        event: str,
        node_id: int,
        packet: Packet,
        detail: str = "",
    ) -> None:
        """Consume a trace event emitted by DCFMultiHopMac."""
        key = self._key(packet)
        context = self._hop_contexts.get(key)

        if event == "DIFS_START":
            self.difs_starts += 1
            self.packet_difs_counts[int(packet.packet_id)] += 1
            if context is not None:
                context.difs_starts += 1
                if context.first_difs_start_at is None:
                    context.first_difs_start_at = float(time)
            return

        if event == "BACKOFF_START":
            self.backoff_starts += 1
            self.competition_attempts += 1
            self.packet_competition_counts[int(packet.packet_id)] += 1
            match = self._SLOTS_PATTERN.search(detail)
            slots = int(match.group(1)) if match else 0
            self.selected_backoff_slots += slots
            if context is not None:
                context.competition_attempts += 1
                context.selected_backoff_slots += slots
            return

        if event == "BACKOFF_TICK":
            self.consumed_backoff_slots += 1
            if context is not None:
                context.consumed_backoff_slots += 1
            return

        if event == "BACKOFF_FREEZE":
            self.backoff_freezes += 1
            if context is not None:
                context.backoff_freezes += 1
            return

        if event == "BACKOFF_RESUME":
            self.backoff_resumes += 1
            return

        if event == "TX_START":
            if context is not None:
                context.last_tx_start_at = float(time)
            return

        if event == "COLLISION":
            self.collided_packet_attempts += 1
            return

        if event == "ACK_TIMEOUT":
            self.ack_timeouts += 1
            return

    def record_retry(self, packet: Packet) -> None:
        """Interface used by Day06 _record_retry_metric()."""
        self.retransmissions += 1
        self.packet_retry_counts[int(packet.packet_id)] += 1

    def record_retransmission(self, packet: Packet) -> None:
        self.record_retry(packet)

    def record_dropped(self, packet: Packet) -> None:
        """Interface used by Day04/Day06 metric compatibility hooks."""
        self.dropped_packets += 1

    def record_hop_success(
        self,
        packet: Packet,
        *,
        sender: int,
        receiver: int,
        ack_at: float,
    ) -> HopMetrics:
        """Close the current-hop context after a successful ACK."""
        key = self._key(packet)
        context = self._hop_contexts.pop(key, None)
        if context is None:
            raise RuntimeError(
                f"Missing hop context for packet={packet.packet_id}, "
                f"hop={packet.current_hop_index}."
            )
        if context.first_difs_start_at is None:
            raise RuntimeError("A successful hop must have a DIFS_START event.")
        if context.last_tx_start_at is None:
            raise RuntimeError("A successful hop must have a TX_START event.")

        first_difs = context.first_difs_start_at
        tx_start = context.last_tx_start_at
        ack_time = float(ack_at)

        record = HopMetrics(
            packet_id=int(packet.packet_id),
            hop_index=int(packet.current_hop_index),
            sender=int(sender),
            receiver=int(receiver),
            queue_enter_at=context.queue_enter_at,
            first_difs_start_at=first_difs,
            successful_tx_start_at=tx_start,
            ack_at=ack_time,
            queue_delay=first_difs - context.queue_enter_at,
            access_delay=tx_start - first_difs,
            tx_ack_delay=ack_time - tx_start,
            hop_delay=ack_time - context.queue_enter_at,
            difs_starts=context.difs_starts,
            competition_attempts=context.competition_attempts,
            selected_backoff_slots=context.selected_backoff_slots,
            consumed_backoff_slots=context.consumed_backoff_slots,
            backoff_freezes=context.backoff_freezes,
            retries=int(getattr(packet, "retries", 0)),
        )
        self.hop_records.append(record)
        self.successful_hops += 1
        return record

    def record_hop_drop(self, packet: Packet) -> None:
        self._hop_contexts.pop(self._key(packet), None)
        self.dropped_hops += 1

    def capture_coordinator(self, coordinator: DCFContentionCoordinator) -> None:
        """Copy shared-medium counters after a simulation run."""
        self.shared_collision_events = int(coordinator.collision_count)

    @property
    def cumulative_backoff_time(self) -> float:
        """Idle countdown time; frozen waiting time is intentionally excluded."""
        return self.consumed_backoff_slots * self.slot_time

    @property
    def average_hop_delay(self) -> float:
        if not self.hop_records:
            return 0.0
        return sum(record.hop_delay for record in self.hop_records) / len(self.hop_records)

    def packet_summary(self, packet_id: int) -> dict[str, int | float]:
        records = [record for record in self.hop_records if record.packet_id == packet_id]
        return {
            "packet_id": int(packet_id),
            "successful_hops": len(records),
            "competition_attempts": int(self.packet_competition_counts.get(packet_id, 0)),
            "difs_starts": int(self.packet_difs_counts.get(packet_id, 0)),
            "retransmissions": int(self.packet_retry_counts.get(packet_id, 0)),
            "cumulative_backoff_slots": sum(
                record.consumed_backoff_slots for record in records
            ),
            "cumulative_backoff_time": sum(
                record.consumed_backoff_slots for record in records
            )
            * self.slot_time,
            "cumulative_hop_delay": sum(record.hop_delay for record in records),
        }

    def summary(self) -> dict[str, float | int]:
        base = dict(super().summary())
        base.update(
            {
                "dropped_packets": int(self.dropped_packets),
                "retransmissions": int(self.retransmissions),
                "successful_hops": int(self.successful_hops),
                "dropped_hops": int(self.dropped_hops),
                "difs_starts": int(self.difs_starts),
                "competition_attempts": int(self.competition_attempts),
                "backoff_starts": int(self.backoff_starts),
                "backoff_resumes": int(self.backoff_resumes),
                "backoff_freezes": int(self.backoff_freezes),
                "selected_backoff_slots": int(self.selected_backoff_slots),
                "consumed_backoff_slots": int(self.consumed_backoff_slots),
                "cumulative_backoff_time": float(self.cumulative_backoff_time),
                "ack_timeouts": int(self.ack_timeouts),
                "shared_collision_events": int(self.shared_collision_events),
                "collided_packet_attempts": int(self.collided_packet_attempts),
                "average_hop_delay": float(self.average_hop_delay),
            }
        )
        return base

    def export_hop_csv(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(HopMetrics.__dataclass_fields__.keys())
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.hop_records:
                writer.writerow(asdict(record))
        return destination

    def export_summary_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(self.summary(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination


class DCFMultiHopNetwork:
    """Map route nodes to their local DCF MAC controllers."""

    def __init__(
        self,
        *,
        simulator: Any,
        metrics: DCFMetricsCollector,
    ) -> None:
        self.simulator = simulator
        self.metrics = metrics
        self.macs: dict[int, DCFMultiHopMac] = {}
        self.created_packet_ids: set[int] = set()

    def register(self, mac: "DCFMultiHopMac") -> None:
        node_id = int(mac.node.node_id)
        if node_id in self.macs:
            raise ValueError(f"Node {node_id} already has a registered MAC.")
        self.macs[node_id] = mac

    def validate_route(self, packet: Packet) -> None:
        route = tuple(packet.route)
        if len(route) < 2:
            raise ValueError("A DCF packet requires a route containing at least one hop.")
        for sender, receiver in zip(route[:-1], route[1:]):
            mac = self.macs.get(int(sender))
            if mac is None:
                raise ValueError(f"Route sender node {sender} has no registered MAC.")
            if int(receiver) not in mac.node.neighbors:
                raise ValueError(f"Route edge {sender}->{receiver} is not a neighbor link.")

    def schedule_source_packet(self, packet: Packet, at: float | None = None) -> None:
        self.validate_route(packet)
        source_mac = self.macs.get(int(packet.source))
        if source_mac is None:
            raise ValueError(f"Source node {packet.source} has no registered MAC.")
        source_mac.schedule_packet_arrival(packet, at=at)

    def forward_packet(self, packet: Packet, *, at: float) -> None:
        relay_mac = self.macs.get(int(packet.current_node))
        if relay_mac is None:
            raise RuntimeError(
                f"Relay node {packet.current_node} has no registered DCF MAC."
            )
        relay_mac.schedule_forwarded_arrival(packet, at=at)


class DCFMultiHopMac(DCFContentionMac):
    """Day06 contention MAC with ACK-driven fixed-route forwarding."""

    def __init__(
        self,
        *args: Any,
        network: DCFMultiHopNetwork,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.network = network
        self.network.register(self)

    def _trace(self, event: str, packet: Packet, detail: str = "") -> None:
        super()._trace(event, packet, detail)
        if isinstance(self.metrics, DCFMetricsCollector):
            self.metrics.observe_mac_event(
                time=self.now,
                event=event,
                node_id=int(self.node.node_id),
                packet=packet,
                detail=detail,
            )

    def on_packet_arrival(self, packet: Packet) -> None:
        self._enqueue_arrival(packet, event="PACKET_ARRIVAL", count_created=True)

    def schedule_forwarded_arrival(self, packet: Packet, *, at: float) -> None:
        if at < self.now:
            raise ValueError("Forwarded packet arrival cannot be scheduled in the past.")
        self._schedule_at(
            at,
            lambda: self._enqueue_arrival(
                packet,
                event="FORWARD_ARRIVAL",
                count_created=False,
            ),
            event_type="FORWARD_ARRIVAL",
            priority=self.PRIORITY_PACKET_ARRIVAL,
        )

    def _enqueue_arrival(
        self,
        packet: Packet,
        *,
        event: str,
        count_created: bool,
    ) -> None:
        if int(packet.current_node) != int(self.node.node_id):
            raise RuntimeError(
                f"Packet {packet.packet_id} is at route node {packet.current_node}, "
                f"but arrived at MAC node {self.node.node_id}."
            )

        self._trace(event, packet)

        if count_created and packet.packet_id not in self.network.created_packet_ids:
            self._record_metric(
                ("record_packet_created", "record_created", "record_creation"),
                packet,
                counter_names=("created_packets", "packets_created", "created_count"),
            )
            self.network.created_packet_ids.add(int(packet.packet_id))

        if not self._packet_is_queued(packet):
            if not self.node.enqueue(packet):
                packet.status = PacketStatus.DROPPED
                self._trace("DROPPED", packet, "queue full")
                self._record_metric(
                    ("record_packet_dropped", "record_dropped", "record_drop"),
                    packet,
                    counter_names=("dropped_packets", "packets_dropped", "dropped_count"),
                )
                return

        if isinstance(self.metrics, DCFMetricsCollector):
            self.metrics.record_queue_entry(
                packet,
                node_id=int(self.node.node_id),
                at=self.now,
            )

        if self.node.peek() is packet and self.node.mac_state == MacState.IDLE:
            self._start_difs(packet)

    def _on_ack_success(self, packet: Packet) -> None:
        """Complete one link; then deliver or enqueue at the next relay."""
        self._assert_head_packet(packet)
        self._trace("ACK", packet)

        sender = int(self.node.node_id)
        receiver = packet.next_hop
        if receiver is None:
            raise RuntimeError("ACK success received for a packet already at destination.")

        if isinstance(self.metrics, DCFMetricsCollector):
            self.metrics.record_hop_success(
                packet,
                sender=sender,
                receiver=int(receiver),
                ack_at=self.now,
            )

        dequeued = self.node.dequeue()
        if dequeued is not packet:
            raise RuntimeError("Queue head changed during successful DCF exchange.")

        self.current_cw = self.config.cw_min
        self.current_backoff_slots = None
        self.initial_backoff_slots = None
        self.node.mac_state = MacState.IDLE
        self.phase = self.PHASE_IDLE

        packet.advance_hop()

        if packet.status == PacketStatus.DELIVERED:
            packet.delivered_at = self.now
            self._trace("DELIVERED", packet, f"delay={packet.end_to_end_delay:.9f}s")
            self._record_metric(
                ("record_packet_delivered", "record_delivered", "record_delivery"),
                packet,
                counter_names=("delivered_packets", "packets_delivered", "delivered_count"),
                event_time=self.now,
            )
        else:
            # Retry limit and BEB are hop-local. The completed hop's retry count
            # has already been preserved in HopMetrics and packet_retry_counts.
            packet.retries = 0
            self._trace(
                "FORWARDED",
                packet,
                f"next_sender={packet.current_node}, remaining_hops={packet.remaining_hops}",
            )
            self.network.forward_packet(packet, at=self.now)

        next_packet = self.node.peek()
        if next_packet is not None:
            self._start_difs(next_packet)

    def _drop_after_retry_limit(self, packet: Packet) -> None:
        if isinstance(self.metrics, DCFMetricsCollector):
            self.metrics.record_hop_drop(packet)
        super()._drop_after_retry_limit(packet)


__all__ = [
    "CollisionChannel",
    "DCFContentionCoordinator",
    "DCFMetricsCollector",
    "DCFMultiHopMac",
    "DCFMultiHopNetwork",
    "HopMetrics",
    "SequenceRandom",
]
