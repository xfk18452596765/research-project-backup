"""Day11 Fixed-PRMAC reserved-segment DATA forwarding with per-hop H_ACK.

Scope is deliberately limited to forwarding one packet over one already ACTIVE
Fixed-PRMAC reservation segment:

ACTIVE reservation
→ DATA on reserved link i
→ receiver returns H_ACK
→ after H_ACK reception, continue on reserved link i+1
→ segment endpoint completes this forwarding operation

Day11 does not implement reservation retry/backoff, cross-segment end-to-end
forwarding, DCF/Fixed-PRMAC performance comparison, or reinforcement learning.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY10_CODE = DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

# Day11 must remain first so Day10 imports the Day11-compatible message model.
# Remove existing entries before prepending to avoid the Day10 import-order bug.
_import_paths = [CURRENT_DIR, DAY10_CODE, DAY09_CODE, DAY03_CODE]
for path in _import_paths:
    path_text = str(path)
    while path_text in sys.path:
        sys.path.remove(path_text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_messages import (  # noqa: E402
    PRMACFrame,
    PRMACFrameType,
    ReservationRecord,
    ReservationStatus,
)
from fixed_prmac_conflict import (  # type: ignore  # noqa: E402
    Day10FixedPRMACConfig,
    Day10FixedPRMACMetrics,
    Day10ReservationTable,
    FixedPRMACConflictController,
    ReservationConflictPolicy,
)


@dataclass(frozen=True, slots=True)
class Day11FixedPRMACConfig(Day10FixedPRMACConfig):
    """Day10 configuration plus DATA/H_ACK PHY serialization parameters.

    Defaults intentionally match the existing DCF baseline so later protocol
    comparisons use the same DATA rate, basic rate, MAC header, and ACK size.
    """

    data_rate_bps: float = 2_000_000.0
    basic_rate_bps: float = 1_000_000.0
    data_mac_header_bytes: int = 34
    h_ack_size_bytes: int = 14

    def __post_init__(self) -> None:
        Day10FixedPRMACConfig.__post_init__(self)
        if self.data_rate_bps <= 0 or self.basic_rate_bps <= 0:
            raise ValueError("DATA and basic PHY rates must be positive.")
        if self.data_mac_header_bytes < 0:
            raise ValueError("data_mac_header_bytes cannot be negative.")
        if self.h_ack_size_bytes <= 0:
            raise ValueError("h_ack_size_bytes must be positive.")

    def data_frame_bytes(self, payload_size_bytes: int) -> int:
        if payload_size_bytes <= 0:
            raise ValueError("payload_size_bytes must be positive.")
        return self.data_mac_header_bytes + payload_size_bytes

    def data_tx_time(self, payload_size_bytes: int) -> float:
        return self.data_frame_bytes(payload_size_bytes) * 8 / self.data_rate_bps

    @property
    def h_ack_tx_time(self) -> float:
        return self.h_ack_size_bytes * 8 / self.basic_rate_bps

    def data_link_delay(self, payload_size_bytes: int) -> float:
        return self.data_tx_time(payload_size_bytes) + self.propagation_delay

    @property
    def h_ack_link_delay(self) -> float:
        return self.h_ack_tx_time + self.propagation_delay

    def estimated_segment_forwarding_time(
        self,
        payload_size_bytes: int,
        hops: int,
    ) -> float:
        if hops <= 0:
            raise ValueError("hops must be positive.")
        # Per hop: DATA propagation + SIFS + H_ACK propagation.
        # Between adjacent reserved hops: one additional SIFS before next DATA.
        return (
            hops
            * (
                self.data_link_delay(payload_size_bytes)
                + self.sifs_time
                + self.h_ack_link_delay
            )
            + (hops - 1) * self.sifs_time
        )


class SegmentForwardingStatus(str, Enum):
    """Lifecycle of one Day11 reserved-segment forwarding operation."""

    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


@dataclass(slots=True)
class SegmentForwardingRecord:
    """Observable state for one packet forwarded under one reservation."""

    transfer_id: str
    reservation_id: str
    packet_id: int
    segment_start_index: int
    effective_hops: int
    scheduled_at: float
    status: SegmentForwardingStatus = SegmentForwardingStatus.SCHEDULED
    started_at: float | None = None
    completed_at: float | None = None
    start_packet_hop_index: int = 0
    end_packet_hop_index: int | None = None
    failure_reason: str = ""

    @property
    def forwarding_delay(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return self.completed_at - self.started_at


@dataclass(slots=True)
class Day11FixedPRMACMetrics(Day10FixedPRMACMetrics):
    """Day10 metrics plus reserved-segment DATA/H_ACK measurements."""

    data_frames_sent: int = 0
    data_bytes_sent: int = 0
    h_ack_frames_sent: int = 0
    h_ack_bytes_sent: int = 0
    forwarded_hops: int = 0
    completed_segments: int = 0
    blocked_segments: int = 0
    segment_forwarding_delays: list[float] = field(default_factory=list)

    def record_data(self, *, packet: Packet, config: Day11FixedPRMACConfig) -> None:
        self.data_frames_sent += 1
        self.data_bytes_sent += config.data_frame_bytes(packet.size_bytes)

    def record_h_ack(self, *, config: Day11FixedPRMACConfig) -> None:
        self.h_ack_frames_sent += 1
        self.h_ack_bytes_sent += config.h_ack_size_bytes

    def summary(self, table: Day10ReservationTable) -> dict[str, int | float]:
        payload = Day10FixedPRMACMetrics.summary(self, table)
        average_forwarding_delay = (
            sum(self.segment_forwarding_delays)
            / len(self.segment_forwarding_delays)
            if self.segment_forwarding_delays
            else 0.0
        )
        payload.update(
            {
                "data_frames_sent": self.data_frames_sent,
                "data_bytes_sent": self.data_bytes_sent,
                "h_ack_frames_sent": self.h_ack_frames_sent,
                "h_ack_bytes_sent": self.h_ack_bytes_sent,
                "forwarded_hops": self.forwarded_hops,
                "completed_segments": self.completed_segments,
                "blocked_segments": self.blocked_segments,
                "average_segment_forwarding_delay": average_forwarding_delay,
                "total_frames_sent": (
                    self.control_frames_sent
                    + self.data_frames_sent
                    + self.h_ack_frames_sent
                ),
                "total_bytes_sent": (
                    self.control_bytes_sent
                    + self.data_bytes_sent
                    + self.h_ack_bytes_sent
                ),
            }
        )
        return payload


class FixedPRMACForwardingController(FixedPRMACConflictController):
    """Day10 controller extended only with Day11 continuous segment forwarding."""

    PRIORITY_FORWARD_START = 40
    PRIORITY_DATA_TX = 20
    PRIORITY_DATA_RX = 10
    PRIORITY_H_ACK_TX = 20
    PRIORITY_H_ACK_RX = 10

    def __init__(
        self,
        *,
        simulator: Simulator,
        config: Day11FixedPRMACConfig | None = None,
        adjacency: dict[int, set[int]] | None = None,
        table: Day10ReservationTable | None = None,
        metrics: Day11FixedPRMACMetrics | None = None,
        conflict_policy: ReservationConflictPolicy | None = None,
    ) -> None:
        resolved_config = config or Day11FixedPRMACConfig()
        resolved_table = table or Day10ReservationTable()
        resolved_metrics = metrics or Day11FixedPRMACMetrics()
        super().__init__(
            simulator=simulator,
            config=resolved_config,
            adjacency=adjacency,
            table=resolved_table,
            metrics=resolved_metrics,
            conflict_policy=conflict_policy,
        )
        self.forwarding_records: dict[str, SegmentForwardingRecord] = {}
        self._reservation_transfer_ids: dict[str, str] = {}
        self._forwarding_sequence = 0

    @property
    def config(self) -> Day11FixedPRMACConfig:
        return self._config

    @config.setter
    def config(self, value: Day11FixedPRMACConfig) -> None:
        self._config = value

    @property
    def metrics(self) -> Day11FixedPRMACMetrics:
        return self._metrics

    @metrics.setter
    def metrics(self, value: Day11FixedPRMACMetrics) -> None:
        self._metrics = value

    def schedule_reserved_forwarding(
        self,
        reservation_id: str,
        packet: Packet,
        *,
        at: float | None = None,
    ) -> str:
        """Schedule one packet across one already ACTIVE reservation segment."""

        forwarding_time = self.now if at is None else float(at)
        if forwarding_time < self.now:
            raise ValueError("Reserved forwarding cannot be scheduled in the past.")

        record = self.table.get(reservation_id)
        self._validate_forwarding_request(record, packet, forwarding_time)
        if reservation_id in self._reservation_transfer_ids:
            raise RuntimeError("A reservation may carry only one Day11 packet transfer.")

        self._forwarding_sequence += 1
        transfer_id = f"{reservation_id}:forward-{self._forwarding_sequence}"
        forwarding = SegmentForwardingRecord(
            transfer_id=transfer_id,
            reservation_id=reservation_id,
            packet_id=int(packet.packet_id),
            segment_start_index=record.segment_start_index,
            effective_hops=record.effective_hops,
            scheduled_at=forwarding_time,
            start_packet_hop_index=int(packet.current_hop_index),
        )
        self.forwarding_records[transfer_id] = forwarding
        self._reservation_transfer_ids[reservation_id] = transfer_id
        self.simulator.schedule_at(
            forwarding_time,
            lambda: self._begin_reserved_forwarding(record, packet, forwarding),
            event_type="SEGMENT_FORWARD_START",
            priority=self.PRIORITY_FORWARD_START,
        )
        return transfer_id

    def _validate_forwarding_request(
        self,
        record: ReservationRecord,
        packet: Packet,
        forwarding_time: float,
    ) -> None:
        if record.status != ReservationStatus.ACTIVE:
            raise RuntimeError(
                "Only an ACTIVE reservation may forward DATA, "
                f"got {record.status.value}."
            )
        if record.expires_at is None:
            raise RuntimeError("An ACTIVE reservation must have expires_at.")
        if packet.packet_id != record.packet_id:
            raise ValueError("Packet identifier does not match reservation record.")
        if tuple(int(node_id) for node_id in packet.route) != record.path:
            raise ValueError("Packet route does not match reservation path.")
        if packet.current_hop_index != record.segment_start_index:
            raise ValueError(
                "Packet current_hop_index must equal reservation segment_start_index."
            )
        if int(packet.current_node) != record.initiator:
            raise ValueError("Packet is not located at the reservation initiator.")

        estimated_end = forwarding_time + self.config.estimated_segment_forwarding_time(
            packet.size_bytes,
            record.effective_hops,
        )
        if forwarding_time >= record.expires_at:
            raise RuntimeError("Reservation has already reached its expiration boundary.")
        if estimated_end > record.expires_at + 1e-15:
            raise RuntimeError(
                "Reservation window is too short for the complete DATA/H_ACK segment."
            )

    def _begin_reserved_forwarding(
        self,
        record: ReservationRecord,
        packet: Packet,
        forwarding: SegmentForwardingRecord,
    ) -> None:
        if record.status != ReservationStatus.ACTIVE:
            forwarding.status = SegmentForwardingStatus.BLOCKED
            forwarding.failure_reason = (
                f"reservation_status={record.status.value} at forwarding start"
            )
            self.metrics.blocked_segments += 1
            self._trace(
                "SEGMENT_FORWARD_BLOCKED",
                record,
                node_id=record.initiator,
                detail=forwarding.failure_reason,
            )
            return

        forwarding.status = SegmentForwardingStatus.IN_PROGRESS
        forwarding.started_at = self.now
        self._trace(
            "SEGMENT_FORWARD_START",
            record,
            node_id=record.initiator,
            detail=(
                f"transfer_id={forwarding.transfer_id}, "
                f"effective_hops={record.effective_hops}, "
                f"payload_bytes={packet.size_bytes}"
            ),
        )
        self.simulator.schedule(
            0.0,
            lambda: self._transmit_data(record, packet, forwarding, 0),
            event_type="DATA_TX",
            priority=self.PRIORITY_DATA_TX,
        )

    def _transmit_data(
        self,
        record: ReservationRecord,
        packet: Packet,
        forwarding: SegmentForwardingRecord,
        link_index: int,
    ) -> None:
        link = record.reserved_links[link_index]
        if int(packet.current_node) != link.sender:
            raise RuntimeError("Packet location is inconsistent with reserved DATA sender.")
        if packet.next_hop != link.receiver:
            raise RuntimeError("Packet next hop is inconsistent with reserved DATA receiver.")

        frame = self._make_forwarding_frame(
            PRMACFrameType.DATA,
            record,
            sender=link.sender,
            receiver=link.receiver,
            link_index=link_index,
        )
        self.frames.append(frame)
        self.metrics.record_data(packet=packet, config=self.config)
        self._trace(
            "DATA_TX",
            record,
            node_id=link.sender,
            frame_type=frame.frame_type.value,
            detail=(
                f"{link.sender}->{link.receiver}, link_index={link_index}, "
                f"payload_bytes={packet.size_bytes}"
            ),
        )
        self.simulator.schedule(
            self.config.data_link_delay(packet.size_bytes),
            lambda: self._receive_data(
                record,
                packet,
                forwarding,
                link_index,
                frame,
            ),
            event_type="DATA_RX",
            priority=self.PRIORITY_DATA_RX,
        )

    def _receive_data(
        self,
        record: ReservationRecord,
        packet: Packet,
        forwarding: SegmentForwardingRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        link = record.reserved_links[link_index]
        self._trace(
            "DATA_RX",
            record,
            node_id=link.receiver,
            frame_type=frame.frame_type.value,
            detail=f"from={link.sender}, link_index={link_index}",
        )
        packet.advance_hop()
        self.metrics.forwarded_hops += 1
        if packet.status == PacketStatus.DELIVERED and packet.delivered_at is None:
            packet.delivered_at = self.now

        self.simulator.schedule(
            self.config.sifs_time,
            lambda: self._transmit_h_ack(
                record,
                packet,
                forwarding,
                link_index,
            ),
            event_type="H_ACK_TX",
            priority=self.PRIORITY_H_ACK_TX,
        )

    def _transmit_h_ack(
        self,
        record: ReservationRecord,
        packet: Packet,
        forwarding: SegmentForwardingRecord,
        link_index: int,
    ) -> None:
        link = record.reserved_links[link_index]
        frame = self._make_forwarding_frame(
            PRMACFrameType.H_ACK,
            record,
            sender=link.receiver,
            receiver=link.sender,
            link_index=link_index,
        )
        self.frames.append(frame)
        self.metrics.record_h_ack(config=self.config)
        self._trace(
            "H_ACK_TX",
            record,
            node_id=link.receiver,
            frame_type=frame.frame_type.value,
            detail=f"{link.receiver}->{link.sender}, link_index={link_index}",
        )
        self.simulator.schedule(
            self.config.h_ack_link_delay,
            lambda: self._receive_h_ack(
                record,
                packet,
                forwarding,
                link_index,
                frame,
            ),
            event_type="H_ACK_RX",
            priority=self.PRIORITY_H_ACK_RX,
        )

    def _receive_h_ack(
        self,
        record: ReservationRecord,
        packet: Packet,
        forwarding: SegmentForwardingRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        link = record.reserved_links[link_index]
        self._trace(
            "H_ACK_RX",
            record,
            node_id=link.sender,
            frame_type=frame.frame_type.value,
            detail=f"from={link.receiver}, link_index={link_index}",
        )

        if link_index + 1 < record.effective_hops:
            self.simulator.schedule(
                self.config.sifs_time,
                lambda: self._transmit_data(
                    record,
                    packet,
                    forwarding,
                    link_index + 1,
                ),
                event_type="DATA_TX",
                priority=self.PRIORITY_DATA_TX,
            )
            return

        forwarding.status = SegmentForwardingStatus.COMPLETED
        forwarding.completed_at = self.now
        forwarding.end_packet_hop_index = int(packet.current_hop_index)
        delay = forwarding.forwarding_delay
        if delay is None:
            raise RuntimeError("Completed forwarding must expose a delay.")
        self.metrics.completed_segments += 1
        self.metrics.segment_forwarding_delays.append(delay)
        self._trace(
            "SEGMENT_FORWARD_COMPLETE",
            record,
            node_id=record.endpoint,
            detail=(
                f"transfer_id={forwarding.transfer_id}, "
                f"forwarded_hops={record.effective_hops}, "
                f"packet_node={packet.current_node}, "
                f"packet_status={packet.status.value}, "
                f"forwarding_delay={delay:.9f}s"
            ),
        )

    def _make_forwarding_frame(
        self,
        frame_type: PRMACFrameType,
        record: ReservationRecord,
        *,
        sender: int,
        receiver: int,
        link_index: int,
    ) -> PRMACFrame:
        if frame_type not in (PRMACFrameType.DATA, PRMACFrameType.H_ACK):
            raise ValueError("Day11 forwarding frame must be DATA or H_ACK.")
        return PRMACFrame(
            frame_type=frame_type,
            flow_id=record.flow_id,
            packet_id=record.packet_id,
            sender=sender,
            receiver=receiver,
            path=record.path,
            segment_start_index=record.segment_start_index,
            requested_hops=record.requested_hops,
            effective_hops=record.effective_hops,
            priority=record.priority,
            duration=record.duration,
            created_at=self.now,
            reserved_links=(record.reserved_links[link_index],),
        )

    def forwarding_snapshot(self) -> list[dict[str, object]]:
        snapshot: list[dict[str, object]] = []
        for forwarding in self.forwarding_records.values():
            item = asdict(forwarding)
            item["status"] = forwarding.status.value
            item["forwarding_delay"] = forwarding.forwarding_delay
            snapshot.append(item)
        return snapshot

    def export_forwarding_summary_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": asdict(self.config),
            "metrics": self.metrics.summary(self.table),
            "forwardings": self.forwarding_snapshot(),
            "reservations": self.conflict_snapshot(),
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination


__all__ = [
    "Day11FixedPRMACConfig",
    "Day11FixedPRMACMetrics",
    "FixedPRMACForwardingController",
    "SegmentForwardingRecord",
    "SegmentForwardingStatus",
]
