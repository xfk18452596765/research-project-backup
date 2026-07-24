"""Day06 DCF extension: two-node collision, ACK timeout, BEB and retry.

This module builds on the Day05 busy-sensing/backoff-freeze controller while
keeping Day03-Day05 files unchanged.  It adds a collision-aware shared medium
and a slot resolver so that stations whose counters reach zero in the same slot
start together and collide, instead of one station incorrectly seeing the
other's same-slot transmission first.

Implemented in Day06:
- two or more single-hop senders sharing one collision domain;
- simultaneous transmission-intent arbitration at slot boundaries;
- DATA collision and missing ACK;
- ACK timeout;
- packet retry counter;
- binary exponential contention-window update;
- finite retry limit and drop;
- eventual retransmission after stations choose different backoff values.

Not implemented: hidden terminals, capture effect, channel errors unrelated to
collision, RTS/CTS, multi-hop forwarding, path reservation, or RL.
"""

from __future__ import annotations

import inspect
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

_DAILY_DIR = Path(__file__).resolve().parents[2]
_DAY03_CODE = _DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
_DAY04_CODE = _DAILY_DIR / "Day04_DCF基础框架" / "code"
_DAY05_CODE = _DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
for _path in (_DAY03_CODE, _DAY04_CODE, _DAY05_CODE):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from node import MacState  # type: ignore  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from dcf_busy_mac import DCFBusyMac  # type: ignore  # noqa: E402


class SequenceRandom:
    """Small deterministic randint provider used by Day06 tests and demo."""

    def __init__(self, values: Iterable[int]) -> None:
        self._values = list(values)
        self._index = 0

    def randint(self, lower: int, upper: int) -> int:
        if self._index >= len(self._values):
            raise RuntimeError("SequenceRandom has no value left for randint().")
        value = int(self._values[self._index])
        self._index += 1
        if not lower <= value <= upper:
            raise ValueError(
                f"Deterministic backoff value {value} is outside [{lower}, {upper}]."
            )
        return value


class CollisionChannel:
    """One shared collision domain with a Day03-like ``is_idle`` interface."""

    def __init__(self) -> None:
        self.owners: set[int] = set()
        self.busy_until = 0.0
        self.collided = False

    def is_idle(self, current_time: float | None = None) -> bool:
        return not self.owners

    def mark_busy(
        self,
        owners: Iterable[int],
        *,
        busy_until: float,
        collided: bool,
    ) -> None:
        if self.owners:
            raise RuntimeError("CollisionChannel is already busy.")
        owners_set = {int(owner) for owner in owners}
        if not owners_set:
            raise ValueError("At least one channel owner is required.")
        self.owners = owners_set
        self.busy_until = float(busy_until)
        self.collided = bool(collided)

    def release(self) -> None:
        self.owners.clear()
        self.collided = False


class DCFContentionCoordinator:
    """Resolve same-slot transmission attempts on the shared medium.

    This object represents shared-medium arbitration in the simulator.  It is
    not a protocol controller and does not choose any station's backoff value.
    Each station still runs its own DCF state machine locally.
    """

    PRIORITY_TX_SLOT_RESOLVE = 35
    PRIORITY_MEDIUM_RELEASE = 5

    def __init__(self, simulator: Any, channel: CollisionChannel, config: Any) -> None:
        self.simulator = simulator
        self.channel = channel
        self.config = config
        self._stations: list[DCFContentionMac] = []
        self._pending: dict[float, list[tuple[DCFContentionMac, Packet]]] = defaultdict(list)
        self._scheduled_resolutions: set[float] = set()
        self.collision_count = 0
        self.successful_exchange_count = 0

    @property
    def now(self) -> float:
        for attribute in ("now", "current_time", "time"):
            if hasattr(self.simulator, attribute):
                return float(getattr(self.simulator, attribute))
        raise AttributeError("Simulator must expose now, current_time, or time.")

    def register(self, station: "DCFContentionMac") -> None:
        if station not in self._stations:
            self._stations.append(station)

    def is_idle(self) -> bool:
        return self.channel.is_idle(self.now)

    def request_tx(self, station: "DCFContentionMac", packet: Packet) -> None:
        """Collect all zero-counter attempts at the current slot boundary."""
        if not self.is_idle():
            station._defer_pending_tx_because_busy(packet)
            return

        slot_time = self.now
        self._pending[slot_time].append((station, packet))
        if slot_time in self._scheduled_resolutions:
            return
        self._scheduled_resolutions.add(slot_time)
        station._schedule_at(
            slot_time,
            lambda timestamp=slot_time: self._resolve_slot(timestamp),
            event_type="TX_SLOT_RESOLVE",
            priority=self.PRIORITY_TX_SLOT_RESOLVE,
        )

    def _resolve_slot(self, timestamp: float) -> None:
        self._scheduled_resolutions.discard(timestamp)
        requests = self._pending.pop(timestamp, [])
        requests = [
            (station, packet)
            for station, packet in requests
            if station.phase == station.PHASE_TX_PENDING
            and station.node.peek() is packet
        ]
        if not requests:
            return
        if not self.is_idle():
            for station, packet in requests:
                station._defer_pending_tx_because_busy(packet)
            return

        if len(requests) == 1:
            self._start_successful_exchange(*requests[0])
        else:
            self._start_collision(requests)

    def _start_successful_exchange(
        self,
        station: "DCFContentionMac",
        packet: Packet,
    ) -> None:
        data_duration = station.config.data_tx_time(packet.size_bytes) + station.config.propagation_delay
        ack_delay = (
            station.config.sifs_time
            + station.config.ack_tx_time
            + station.config.propagation_delay
        )
        ack_time = self.now + data_duration + ack_delay
        self.channel.mark_busy(
            [station.node.node_id],
            busy_until=ack_time,
            collided=False,
        )
        self.successful_exchange_count += 1
        station._begin_transmission(packet, collided=False)
        self._notify_peer_busy(excluded={station})

        station._schedule(
            data_duration,
            lambda: station._on_data_tx_end(packet, collided=False),
            event_type="TX_END",
            priority=station.PRIORITY_TX_END,
        )
        station._schedule(
            data_duration + ack_delay,
            lambda: self._complete_success(station, packet),
            event_type="ACK",
            priority=station.PRIORITY_ACK,
        )

    def _complete_success(
        self,
        station: "DCFContentionMac",
        packet: Packet,
    ) -> None:
        self.channel.release()
        station._on_ack_success(packet)
        self._notify_medium_idle()

    def _start_collision(
        self,
        requests: list[tuple["DCFContentionMac", Packet]],
    ) -> None:
        self.collision_count += 1
        max_data_duration = max(
            station.config.data_tx_time(packet.size_bytes) + station.config.propagation_delay
            for station, packet in requests
        )
        timeout_delay = max(
            station.config.sifs_time
            + station.config.ack_tx_time
            + station.config.propagation_delay
            for station, _ in requests
        )
        self.channel.mark_busy(
            [station.node.node_id for station, _ in requests],
            busy_until=self.now + max_data_duration,
            collided=True,
        )

        request_stations = {station for station, _ in requests}
        for station, packet in requests:
            data_duration = station.config.data_tx_time(packet.size_bytes) + station.config.propagation_delay
            station._begin_transmission(packet, collided=True)
            station._schedule(
                data_duration,
                lambda station=station, packet=packet: station._on_data_tx_end(
                    packet,
                    collided=True,
                ),
                event_type="TX_END",
                priority=station.PRIORITY_TX_END,
            )
            station._schedule(
                max_data_duration + timeout_delay,
                lambda station=station, packet=packet: station._on_ack_timeout(packet),
                event_type="ACK_TIMEOUT",
                priority=station.PRIORITY_ACK,
            )

        self._notify_peer_busy(excluded=request_stations)
        first_station = requests[0][0]
        first_station._schedule(
            max_data_duration,
            self._complete_collision_medium,
            event_type="COLLISION_END",
            priority=self.PRIORITY_MEDIUM_RELEASE,
        )

    def _complete_collision_medium(self) -> None:
        self.channel.release()
        self._notify_medium_idle()

    def _notify_peer_busy(self, *, excluded: set["DCFContentionMac"]) -> None:
        for station in self._stations:
            if station not in excluded:
                station._on_peer_medium_busy()

    def _notify_medium_idle(self) -> None:
        for station in self._stations:
            station._on_shared_medium_idle()


class DCFContentionMac(DCFBusyMac):
    """Per-station DCF with collision-driven ACK timeout and retransmission."""

    def __init__(
        self,
        *args: Any,
        coordinator: DCFContentionCoordinator,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.coordinator = coordinator
        self.coordinator.register(self)
        self.max_cw_observed = self.current_cw
        self.collision_attempts = 0

    def _channel_is_idle(self) -> bool:
        return self.coordinator.is_idle()

    def _expire_backoff(self, packet: Packet) -> None:
        self.phase = self.PHASE_TX_PENDING
        self._trace("BACKOFF_EXPIRE", packet)
        self.coordinator.request_tx(self, packet)

    def _defer_pending_tx_because_busy(self, packet: Packet) -> None:
        self._contention_generation += 1
        self.phase = self.PHASE_WAIT_CHANNEL
        self._trace(
            "BACKOFF_FREEZE",
            packet,
            f"remaining_slots={self.current_backoff_slots or 0}, reason=busy_at_tx_boundary",
        )

    def _begin_transmission(self, packet: Packet, *, collided: bool) -> None:
        self._assert_head_packet(packet)
        self.phase = self.PHASE_TRANSMITTING
        self.node.mac_state = MacState.TRANSMITTING
        packet.status = PacketStatus.TRANSMITTING
        data_duration = self.config.data_tx_time(packet.size_bytes) + self.config.propagation_delay
        self._trace(
            "TX_START",
            packet,
            f"duration={data_duration:.9f}s, collided={collided}",
        )
        if collided:
            self.collision_attempts += 1
            self._trace("COLLISION", packet, "simultaneous transmission in the same slot")

    def _on_data_tx_end(self, packet: Packet, *, collided: bool) -> None:
        self._assert_head_packet(packet)
        self.node.mac_state = MacState.WAIT_ACK
        self.phase = self.PHASE_WAIT_ACK
        self._trace("TX_END", packet, f"collided={collided}")

    def _on_ack_success(self, packet: Packet) -> None:
        super()._on_ack(packet)

    def _on_ack_timeout(self, packet: Packet) -> None:
        if self.node.peek() is not packet or self.phase != self.PHASE_WAIT_ACK:
            return
        self._trace("ACK_TIMEOUT", packet)
        self._increment_packet_retry(packet)
        self._record_retry_metric(packet)

        if int(getattr(packet, "retries", 0)) > self.config.retry_limit:
            self._drop_after_retry_limit(packet)
            return

        previous_cw = self.current_cw
        self.current_cw = min(2 * self.current_cw + 1, self.config.cw_max)
        self.max_cw_observed = max(self.max_cw_observed, self.current_cw)
        self.current_backoff_slots = None
        packet.status = PacketStatus.CONTENDING
        self.node.mac_state = MacState.BACKING_OFF
        self._trace(
            "CW_UPDATE",
            packet,
            f"old={previous_cw}, new={self.current_cw}, retry={packet.retries}",
        )
        self._start_difs(packet)

    def _drop_after_retry_limit(self, packet: Packet) -> None:
        dropped_status = getattr(PacketStatus, "DROPPED", None)
        if dropped_status is not None:
            packet.status = dropped_status
        dequeued = self.node.dequeue()
        if dequeued is not packet:
            raise RuntimeError("Queue head changed before retry-limit drop.")
        self._trace(
            "DROPPED",
            packet,
            f"retry_limit={self.config.retry_limit}, retries={packet.retries}",
        )
        self._record_metric(
            ("record_packet_dropped", "record_dropped", "record_drop"),
            packet,
            counter_names=("dropped_packets", "packets_dropped", "dropped_count"),
        )
        self.current_cw = self.config.cw_min
        self.current_backoff_slots = None
        self.node.mac_state = MacState.IDLE
        self.phase = self.PHASE_IDLE
        next_packet = self.node.peek()
        if next_packet is not None:
            self._start_difs(next_packet)

    def _on_peer_medium_busy(self) -> None:
        packet = self.node.peek()
        if packet is None:
            return
        if self.phase == self.PHASE_DIFS:
            self._interrupt_for_busy(packet, during="DIFS")
        elif self.phase == self.PHASE_BACKOFF:
            self._interrupt_for_busy(packet, during="BACKOFF")
        elif self.phase == self.PHASE_TX_PENDING:
            self._defer_pending_tx_because_busy(packet)
        elif self.phase == self.PHASE_IDLE:
            self.phase = self.PHASE_WAIT_CHANNEL

    def _on_shared_medium_idle(self) -> None:
        packet = self.node.peek()
        if packet is not None and self.phase == self.PHASE_WAIT_CHANNEL:
            self._start_difs(packet)

    @staticmethod
    def _increment_packet_retry(packet: Packet) -> None:
        method = getattr(packet, "increment_retry", None)
        if callable(method):
            method()
        else:
            packet.retries = int(getattr(packet, "retries", 0)) + 1

    def _record_retry_metric(self, packet: Packet) -> None:
        if self.metrics is None:
            return
        for name in ("record_retry", "record_retransmission", "record_packet_retry"):
            method = getattr(self.metrics, name, None)
            if not callable(method):
                continue
            signature = inspect.signature(method)
            for args in ((packet,), (1,), ()):
                try:
                    signature.bind(*args)
                except TypeError:
                    continue
                method(*args)
                return
        for name in ("total_retries", "retransmissions", "retry_count"):
            if hasattr(self.metrics, name):
                setattr(self.metrics, name, int(getattr(self.metrics, name)) + 1)
                return
