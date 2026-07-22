"""Minimum single-hop, no-contention DCF implementation for Day04.

Implemented chain:
PACKET_ARRIVAL -> DIFS -> random backoff -> TX_START -> TX_END -> ACK -> DELIVERED

This file intentionally does not implement collision handling, hidden terminals,
RTS/CTS, multi-hop forwarding, path reservation, or reinforcement learning.
"""

from __future__ import annotations

import inspect
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Reuse Day03 core objects rather than duplicating them in Day04.
_DAY03_CODE = Path(__file__).resolve().parents[2] / "Day03_仿真架构与事件设计" / "code"
if _DAY03_CODE.exists() and str(_DAY03_CODE) not in sys.path:
    sys.path.insert(0, str(_DAY03_CODE))

from channel import Channel  # type: ignore  # noqa: E402
from metrics import MetricsCollector  # type: ignore  # noqa: E402
from node import MacState, Node  # type: ignore  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402

from dcf_config import DCFConfig


@dataclass(frozen=True, slots=True)
class DCFTraceRecord:
    """One observable protocol transition."""

    time: float
    event: str
    node_id: int
    packet_id: int
    detail: str = ""


class DCFMac:
    """Single-node DCF controller connected to Day03 core components."""

    PRIORITY_TX_END = 0
    PRIORITY_ACK = 10
    PRIORITY_TX_START = 20
    PRIORITY_BACKOFF = 30
    PRIORITY_PACKET_ARRIVAL = 40

    def __init__(
        self,
        simulator: Simulator,
        node: Node,
        channel: Channel,
        metrics: MetricsCollector | None = None,
        config: DCFConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.simulator = simulator
        self.node = node
        self.channel = channel
        self.metrics = metrics
        self.config = config or DCFConfig()
        self.rng = rng or random.Random(self.config.random_seed)

        self.current_cw = self.config.cw_min
        self.current_backoff_slots: int | None = None
        self.trace: list[DCFTraceRecord] = []
        self._created_packet_ids: set[int] = set()

    @property
    def now(self) -> float:
        """Return current simulation time across small Day03 API variations."""
        for attribute in ("now", "current_time", "time"):
            if hasattr(self.simulator, attribute):
                return float(getattr(self.simulator, attribute))
        raise AttributeError("Simulator must expose now, current_time, or time.")

    def schedule_packet_arrival(self, packet: Packet, at: float | None = None) -> None:
        """Schedule the external PACKET_ARRIVAL event."""
        arrival_time = packet.created_at if at is None else at
        if arrival_time < self.now:
            raise ValueError("Packet arrival cannot be scheduled in the past.")

        self._schedule_at(
            arrival_time,
            lambda: self.on_packet_arrival(packet),
            event_type="PACKET_ARRIVAL",
            priority=self.PRIORITY_PACKET_ARRIVAL,
        )

    def on_packet_arrival(self, packet: Packet) -> None:
        """Queue a packet and start DCF if it becomes the head-of-line packet."""
        self._trace("PACKET_ARRIVAL", packet)

        if packet.packet_id not in self._created_packet_ids:
            self._record_metric(
                ("record_packet_created", "record_created", "record_creation"),
                packet,
                counter_names=("created_packets", "packets_created", "created_count"),
            )
            self._created_packet_ids.add(packet.packet_id)

        # Day03 documentation allows either node.enqueue(packet) before this call
        # or letting this entry point perform the enqueue itself.
        if not self._packet_is_queued(packet):
            if not self.node.enqueue(packet):
                self._trace("DROPPED", packet, "queue full")
                self._record_metric(
                    ("record_packet_dropped", "record_dropped", "record_drop"),
                    packet,
                    counter_names=("dropped_packets", "packets_dropped", "dropped_count"),
                )
                return

        if self.node.peek() is packet and self.node.mac_state == MacState.IDLE:
            self._start_difs(packet)

    def _start_difs(self, packet: Packet) -> None:
        if not self._channel_is_idle():
            raise RuntimeError(
                "Day04 phase 1 assumes an idle channel; busy-channel deferral is not implemented yet."
            )

        packet.status = PacketStatus.CONTENDING
        self.node.mac_state = MacState.BACKING_OFF
        self._trace("DIFS_START", packet, f"duration={self.config.difs_time:.9f}s")
        self._schedule(
            self.config.difs_time,
            lambda: self._on_difs_end(packet),
            event_type="DIFS_END",
            priority=self.PRIORITY_BACKOFF,
        )

    def _on_difs_end(self, packet: Packet) -> None:
        self._assert_head_packet(packet)
        if not self._channel_is_idle():
            raise RuntimeError("Channel became busy during DIFS; this belongs to Day04 phase 2.")

        self._trace("DIFS_END", packet)
        self.current_backoff_slots = self.rng.randint(0, self.current_cw)
        backoff_delay = self.current_backoff_slots * self.config.slot_time
        self._trace(
            "BACKOFF_START",
            packet,
            f"slots={self.current_backoff_slots}, delay={backoff_delay:.9f}s",
        )
        self._schedule(
            backoff_delay,
            lambda: self._on_backoff_expire(packet),
            event_type="BACKOFF_EXPIRE",
            priority=self.PRIORITY_BACKOFF,
        )

    def _on_backoff_expire(self, packet: Packet) -> None:
        self._assert_head_packet(packet)
        if not self._channel_is_idle():
            raise RuntimeError("Channel became busy during backoff; freeze/resume is not in phase 1.")

        self._trace("BACKOFF_EXPIRE", packet)
        self._schedule(
            0.0,
            lambda: self._on_tx_start(packet),
            event_type="TX_START",
            priority=self.PRIORITY_TX_START,
        )

    def _on_tx_start(self, packet: Packet) -> None:
        self._assert_head_packet(packet)
        if not self._channel_is_idle():
            raise RuntimeError("TX_START requires an idle channel in Day04 phase 1.")

        data_duration = self.config.data_tx_time(packet.size_bytes) + self.config.propagation_delay
        self._occupy_channel(data_duration)
        self.node.mac_state = MacState.TRANSMITTING
        packet.status = PacketStatus.TRANSMITTING
        self._trace("TX_START", packet, f"duration={data_duration:.9f}s")
        self._schedule(
            data_duration,
            lambda: self._on_tx_end(packet),
            event_type="TX_END",
            priority=self.PRIORITY_TX_END,
        )

    def _on_tx_end(self, packet: Packet) -> None:
        self._release_channel()
        self.node.mac_state = MacState.WAIT_ACK
        self._trace("TX_END", packet)

        ack_delay = self.config.sifs_time + self.config.ack_tx_time + self.config.propagation_delay
        self._schedule(
            ack_delay,
            lambda: self._on_ack(packet),
            event_type="ACK",
            priority=self.PRIORITY_ACK,
        )

    def _on_ack(self, packet: Packet) -> None:
        self._assert_head_packet(packet)
        self._trace("ACK", packet)

        packet.advance_hop()
        if packet.status != PacketStatus.DELIVERED:
            raise RuntimeError("Day04 phase 1 only supports a one-hop route.")

        packet.delivered_at = self.now
        dequeued = self.node.dequeue()
        if dequeued is not packet:
            raise RuntimeError("Node queue head changed unexpectedly during DCF transmission.")

        self.current_cw = self.config.cw_min
        self.current_backoff_slots = None
        self.node.mac_state = MacState.IDLE
        self._trace("DELIVERED", packet, f"delay={packet.end_to_end_delay:.9f}s")
        self._record_metric(
            ("record_packet_delivered", "record_delivered", "record_delivery"),
            packet,
            counter_names=("delivered_packets", "packets_delivered", "delivered_count"),
            event_time=self.now,
        )

        next_packet = self.node.peek()
        if next_packet is not None:
            self._start_difs(next_packet)

    def on_tx_success(self, packet: Packet) -> None:
        """Compatibility hook retained for later ACK-driven refactoring."""
        if packet.status != PacketStatus.DELIVERED:
            raise RuntimeError("on_tx_success is called after ACK delivery in phase 1.")

    def on_tx_failure(self, packet: Packet) -> None:
        """Reserved interface for the next DCF stage; failures are not modeled yet."""
        raise NotImplementedError("Retransmission and binary exponential backoff are not in phase 1.")

    def _packet_is_queued(self, packet: Packet) -> bool:
        queue = getattr(self.node, "tx_queue", ())
        return any(item is packet for item in queue)

    def _assert_head_packet(self, packet: Packet) -> None:
        if self.node.peek() is not packet:
            raise RuntimeError("DCF may only operate on the node's head-of-line packet.")

    def _trace(self, event: str, packet: Packet, detail: str = "") -> None:
        self.trace.append(
            DCFTraceRecord(
                time=self.now,
                event=event,
                node_id=self.node.node_id,
                packet_id=packet.packet_id,
                detail=detail,
            )
        )

    def _schedule(self, delay: float, callback: Callable[[], None], *, event_type: str, priority: int) -> Any:
        """Call Day03 Simulator.schedule while tolerating minor keyword differences."""
        method = self.simulator.schedule
        parameters = inspect.signature(method).parameters
        kwargs: dict[str, Any] = {}
        if "delay" in parameters:
            kwargs["delay"] = delay
        if "callback" in parameters:
            kwargs["callback"] = callback
        if "priority" in parameters:
            kwargs["priority"] = priority
        if "event_type" in parameters:
            kwargs["event_type"] = event_type
        if "name" in parameters and "event_type" not in parameters:
            kwargs["name"] = event_type
        try:
            return method(**kwargs)
        except TypeError:
            return method(delay, callback, priority=priority, event_type=event_type)

    def _schedule_at(self, time: float, callback: Callable[[], None], *, event_type: str, priority: int) -> Any:
        method = getattr(self.simulator, "schedule_at", None)
        if method is None:
            return self._schedule(time - self.now, callback, event_type=event_type, priority=priority)

        parameters = inspect.signature(method).parameters
        kwargs: dict[str, Any] = {}
        for key in ("time", "at", "event_time"):
            if key in parameters:
                kwargs[key] = time
                break
        if "callback" in parameters:
            kwargs["callback"] = callback
        if "priority" in parameters:
            kwargs["priority"] = priority
        if "event_type" in parameters:
            kwargs["event_type"] = event_type
        if "name" in parameters and "event_type" not in parameters:
            kwargs["name"] = event_type
        try:
            return method(**kwargs)
        except TypeError:
            return method(time, callback, priority=priority, event_type=event_type)

    def _channel_is_idle(self) -> bool:
        method = self.channel.is_idle
        try:
            return bool(method(self.now))
        except TypeError:
            return bool(method())

    def _occupy_channel(self, duration: float) -> None:
        method = self.channel.occupy
        parameters = inspect.signature(method).parameters
        values = {
            "owner": self.node.node_id,
            "node_id": self.node.node_id,
            "start_time": self.now,
            "current_time": self.now,
            "now": self.now,
            "duration": duration,
            "busy_until": self.now + duration,
            "until": self.now + duration,
        }
        kwargs = {name: values[name] for name in parameters if name in values}
        try:
            method(**kwargs)
            return
        except TypeError:
            pass

        for args in (
            (self.node.node_id, self.now, duration),
            (self.node.node_id, self.now + duration),
            (self.node.node_id, duration),
        ):
            try:
                method(*args)
                return
            except TypeError:
                continue
        raise TypeError("Unsupported Channel.occupy signature.")

    def _release_channel(self) -> None:
        method = self.channel.release
        try:
            method(self.node.node_id)
        except TypeError:
            method()

    def _record_metric(
        self,
        method_names: tuple[str, ...],
        packet: Packet,
        *,
        counter_names: tuple[str, ...],
        event_time: float | None = None,
    ) -> None:
        """Record a metric while matching the actual Day03 method signature.

        Day03 ``MetricsCollector.record_delivered`` requires both
        ``packet`` and ``delivered_at``. Other small collectors may expose a
        one-argument or zero-argument method, so signature binding is used
        before invocation instead of catching a TypeError raised by the
        metric method itself.
        """
        if self.metrics is None:
            return

        for name in method_names:
            method = getattr(self.metrics, name, None)
            if not callable(method):
                continue

            candidates: list[tuple[Any, ...]] = []
            if event_time is not None:
                candidates.append((packet, event_time))
            candidates.extend(((packet,), ()))

            signature = inspect.signature(method)
            for args in candidates:
                try:
                    signature.bind(*args)
                except TypeError:
                    continue
                method(*args)
                return

            raise TypeError(
                f"Unsupported MetricsCollector.{name} signature: {signature}"
            )

        # Last-resort compatibility for very small Day03 collectors.
        for name in counter_names:
            if hasattr(self.metrics, name):
                setattr(self.metrics, name, int(getattr(self.metrics, name)) + 1)
                return
