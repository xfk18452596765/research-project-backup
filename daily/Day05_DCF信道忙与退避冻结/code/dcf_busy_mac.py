"""Day05 DCF extension: busy-channel deferral and backoff freeze/resume.

This module extends the Day04 minimum single-hop DCF implementation without
changing Day03 or Day04 files.  It still models one sender and one receiver.
An external busy interval represents another transmission already occupying the
shared medium; it is not a second DCF station and cannot collide with this node.

Implemented additions:
- defer when the medium is busy at packet arrival;
- restart DIFS if the medium becomes busy during DIFS;
- freeze the remaining backoff counter when the medium becomes busy;
- after the medium is idle, wait a full DIFS and resume the remaining counter.

Not implemented: collision, ACK timeout, retransmission, binary exponential
backoff, hidden terminals, RTS/CTS, multi-hop forwarding, path reservation, or RL.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

_DAILY_DIR = Path(__file__).resolve().parents[2]
_DAY03_CODE = _DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
_DAY04_CODE = _DAILY_DIR / "Day04_DCF基础框架" / "code"
for _path in (_DAY03_CODE, _DAY04_CODE):
    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from node import MacState  # type: ignore  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from dcf_mac import DCFMac  # type: ignore  # noqa: E402


class DCFBusyMac(DCFMac):
    """DCF controller with busy-medium deferral and slot-level backoff."""

    PRIORITY_EXTERNAL_MEDIUM = 5
    PHASE_IDLE = "IDLE"
    PHASE_WAIT_CHANNEL = "WAIT_CHANNEL"
    PHASE_DIFS = "DIFS"
    PHASE_BACKOFF = "BACKOFF"
    PHASE_TX_PENDING = "TX_PENDING"
    PHASE_TRANSMITTING = "TRANSMITTING"
    PHASE_WAIT_ACK = "WAIT_ACK"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.phase = self.PHASE_IDLE
        self.initial_backoff_slots: int | None = None
        self._contention_generation = 0
        self._external_owner: int | str | None = None

    def schedule_external_busy(
        self,
        start_time: float,
        duration: float,
        *,
        owner: int | str = -1,
    ) -> None:
        """Schedule one non-colliding external medium-busy interval.

        The interval is an exogenous workload used to verify carrier sensing and
        backoff freeze/resume. Overlapping busy intervals are intentionally not
        supported in Day05.
        """
        if start_time < self.now:
            raise ValueError("External busy interval cannot start in the past.")
        if duration <= 0:
            raise ValueError("External busy duration must be positive.")

        self._schedule_at(
            start_time,
            lambda: self._on_external_busy_start(duration, owner),
            event_type="EXTERNAL_BUSY_START",
            priority=self.PRIORITY_EXTERNAL_MEDIUM,
        )
        self._schedule_at(
            start_time + duration,
            lambda: self._on_external_busy_end(owner),
            event_type="EXTERNAL_BUSY_END",
            priority=self.PRIORITY_EXTERNAL_MEDIUM,
        )

    def _start_difs(self, packet: Packet) -> None:
        """Start or restart DIFS; defer instead of raising when busy."""
        self._assert_head_packet(packet)
        packet.status = PacketStatus.CONTENDING
        self.node.mac_state = MacState.BACKING_OFF
        self._contention_generation += 1

        if not self._channel_is_idle():
            self.phase = self.PHASE_WAIT_CHANNEL
            self._trace(
                "CHANNEL_BUSY_WAIT",
                packet,
                f"remaining_slots={self.current_backoff_slots}",
            )
            return

        self.phase = self.PHASE_DIFS
        generation = self._contention_generation
        reason = "initial" if self.current_backoff_slots is None else "resume_after_busy"
        self._trace(
            "DIFS_START",
            packet,
            f"duration={self.config.difs_time:.9f}s, reason={reason}",
        )
        self._schedule(
            self.config.difs_time,
            lambda: self._on_difs_end_busy_aware(packet, generation),
            event_type="DIFS_END",
            priority=self.PRIORITY_BACKOFF,
        )

    def _on_difs_end_busy_aware(self, packet: Packet, generation: int) -> None:
        """Finish DIFS if it was not invalidated by a busy-medium event."""
        if generation != self._contention_generation or self.phase != self.PHASE_DIFS:
            return
        self._assert_head_packet(packet)

        if not self._channel_is_idle():
            self._interrupt_for_busy(packet, during="DIFS")
            return

        self._trace("DIFS_END", packet)
        if self.current_backoff_slots is None:
            self.current_backoff_slots = self.rng.randint(0, self.current_cw)
            self.initial_backoff_slots = self.current_backoff_slots
            self._trace(
                "BACKOFF_START",
                packet,
                f"slots={self.current_backoff_slots}",
            )
        else:
            self._trace(
                "BACKOFF_RESUME",
                packet,
                f"remaining_slots={self.current_backoff_slots}",
            )

        self.phase = self.PHASE_BACKOFF
        if self.current_backoff_slots == 0:
            self._expire_backoff(packet)
            return
        self._schedule_backoff_tick(packet, generation)

    def _schedule_backoff_tick(self, packet: Packet, generation: int) -> None:
        self._schedule(
            self.config.slot_time,
            lambda: self._on_backoff_tick(packet, generation),
            event_type="BACKOFF_TICK",
            priority=self.PRIORITY_BACKOFF,
        )

    def _on_backoff_tick(self, packet: Packet, generation: int) -> None:
        """Consume one slot only while the medium remains idle."""
        if generation != self._contention_generation or self.phase != self.PHASE_BACKOFF:
            return
        self._assert_head_packet(packet)

        if not self._channel_is_idle():
            self._interrupt_for_busy(packet, during="BACKOFF")
            return
        if self.current_backoff_slots is None or self.current_backoff_slots <= 0:
            raise RuntimeError("Backoff tick requires a positive remaining counter.")

        self.current_backoff_slots -= 1
        self._trace(
            "BACKOFF_TICK",
            packet,
            f"remaining_slots={self.current_backoff_slots}",
        )
        if self.current_backoff_slots == 0:
            self._expire_backoff(packet)
            return
        self._schedule_backoff_tick(packet, generation)

    def _expire_backoff(self, packet: Packet) -> None:
        self.phase = self.PHASE_TX_PENDING
        self._trace("BACKOFF_EXPIRE", packet)
        self._schedule(
            0.0,
            lambda: self._on_tx_start(packet),
            event_type="TX_START",
            priority=self.PRIORITY_TX_START,
        )

    def _interrupt_for_busy(self, packet: Packet, *, during: str) -> None:
        self._contention_generation += 1
        self.phase = self.PHASE_WAIT_CHANNEL
        if during == "DIFS":
            self._trace("DIFS_INTERRUPTED", packet, "DIFS must restart after channel idle")
        else:
            self._trace(
                "BACKOFF_FREEZE",
                packet,
                f"remaining_slots={self.current_backoff_slots}",
            )

    def _on_external_busy_start(self, duration: float, owner: int | str) -> None:
        if not self._channel_is_idle():
            raise RuntimeError("Overlapping medium-busy intervals are outside Day05 scope.")
        if self.phase in (
            self.PHASE_TX_PENDING,
            self.PHASE_TRANSMITTING,
            self.PHASE_WAIT_ACK,
        ):
            raise RuntimeError(
                "External busy interval overlaps this node's transmission; "
                "collision handling belongs to the next DCF stage."
            )

        self._occupy_channel_as(owner=owner, duration=duration)
        self._external_owner = owner
        packet = self.node.peek()
        if packet is None:
            return

        self._trace("EXTERNAL_BUSY_START", packet, f"duration={duration:.9f}s")
        if self.phase == self.PHASE_DIFS:
            self._interrupt_for_busy(packet, during="DIFS")
        elif self.phase == self.PHASE_BACKOFF:
            self._interrupt_for_busy(packet, during="BACKOFF")
        elif self.phase == self.PHASE_IDLE:
            self.phase = self.PHASE_WAIT_CHANNEL

    def _on_external_busy_end(self, owner: int | str) -> None:
        if self._external_owner != owner:
            raise RuntimeError("External medium owner does not match the active interval.")
        self._release_channel_as(owner)
        self._external_owner = None

        packet = self.node.peek()
        if packet is None:
            return
        self._trace("EXTERNAL_BUSY_END", packet)
        if self.phase == self.PHASE_WAIT_CHANNEL:
            self._start_difs(packet)

    def _on_tx_start(self, packet: Packet) -> None:
        super()._on_tx_start(packet)
        self.phase = self.PHASE_TRANSMITTING

    def _on_tx_end(self, packet: Packet) -> None:
        super()._on_tx_end(packet)
        self.phase = self.PHASE_WAIT_ACK

    def _on_ack(self, packet: Packet) -> None:
        super()._on_ack(packet)
        if self.node.peek() is None:
            self.phase = self.PHASE_IDLE
            self.initial_backoff_slots = None

    def _occupy_channel_as(self, *, owner: int | str, duration: float) -> None:
        method = self.channel.occupy
        parameters = inspect.signature(method).parameters
        values: dict[str, Any] = {
            "owner": owner,
            "node_id": owner,
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
            (owner, self.now, duration),
            (owner, self.now + duration),
            (owner, duration),
        ):
            try:
                method(*args)
                return
            except TypeError:
                continue
        raise TypeError("Unsupported Channel.occupy signature for external traffic.")

    def _release_channel_as(self, owner: int | str) -> None:
        method = self.channel.release
        parameters = inspect.signature(method).parameters
        values: dict[str, Any] = {
            "owner": owner,
            "node_id": owner,
            "current_time": self.now,
            "now": self.now,
        }
        kwargs = {name: values[name] for name in parameters if name in values}
        try:
            method(**kwargs)
            return
        except TypeError:
            pass

        for args in ((owner,), (self.now,), ()):
            try:
                method(*args)
                return
            except TypeError:
                continue
        raise TypeError("Unsupported Channel.release signature for external traffic.")
