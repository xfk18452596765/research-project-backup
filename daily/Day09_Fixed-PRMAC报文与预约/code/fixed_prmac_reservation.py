"""Day09 Fixed-PRMAC control messages and successful reservation setup.

Scope:
- fixed reservation length K=2 by default;
- fixed initial contention window CWmin=15 as a baseline parameter;
- abstract PR_REQ forward propagation;
- reverse PR_ACK confirmation;
- active reservation table;
- RELEASE propagation and reservation cleanup;
- control overhead and setup-delay metrics.

The caller is assumed to invoke ``schedule_reservation`` after the reservation
initiator has obtained channel access. Day09 intentionally does not implement
reservation conflicts, PR_NACK, continuous DATA forwarding, reservation failure
retries, or reinforcement learning.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

for path in (CURRENT_DIR, DAY03_CODE):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from packet import Packet  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402

from fixed_prmac_messages import (  # noqa: E402
    PRMACFrame,
    PRMACFrameType,
    ReservationRecord,
    ReservationStatus,
    ReservationTraceRecord,
    ReservedLink,
)


@dataclass(frozen=True, slots=True)
class FixedPRMACConfig:
    """Fixed-PRMAC parameters frozen before reinforcement learning."""

    fixed_k: int = 2
    fixed_cw_min: int = 15
    reservation_duration: float = 0.020
    pr_req_size_bytes: int = 36
    pr_ack_size_bytes: int = 24
    release_size_bytes: int = 20
    control_rate_bps: float = 1_000_000.0
    sifs_time: float = 10e-6
    propagation_delay: float = 1e-6

    def __post_init__(self) -> None:
        if self.fixed_k <= 0:
            raise ValueError("fixed_k must be positive.")
        if self.fixed_cw_min < 0:
            raise ValueError("fixed_cw_min cannot be negative.")
        if self.reservation_duration <= 0:
            raise ValueError("reservation_duration must be positive.")
        for name, value in (
            ("pr_req_size_bytes", self.pr_req_size_bytes),
            ("pr_ack_size_bytes", self.pr_ack_size_bytes),
            ("release_size_bytes", self.release_size_bytes),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
        if self.control_rate_bps <= 0:
            raise ValueError("control_rate_bps must be positive.")
        if self.sifs_time < 0 or self.propagation_delay < 0:
            raise ValueError("Timing values cannot be negative.")

    def frame_tx_time(self, frame_type: PRMACFrameType) -> float:
        """Return serialization time for one abstract control frame."""
        sizes = {
            PRMACFrameType.PR_REQ: self.pr_req_size_bytes,
            PRMACFrameType.PR_ACK: self.pr_ack_size_bytes,
            PRMACFrameType.RELEASE: self.release_size_bytes,
        }
        try:
            size_bytes = sizes[frame_type]
        except KeyError as exc:
            raise ValueError(
                f"Day09 does not serialize frame type {frame_type.value}."
            ) from exc
        return size_bytes * 8 / self.control_rate_bps

    def link_delay(self, frame_type: PRMACFrameType) -> float:
        return self.frame_tx_time(frame_type) + self.propagation_delay


class ReservationTable:
    """Reservation lifecycle store without a Day10 conflict policy."""

    def __init__(self) -> None:
        self._records: dict[str, ReservationRecord] = {}

    def add_pending(self, record: ReservationRecord) -> None:
        if record.reservation_id in self._records:
            raise ValueError(
                f"Duplicate reservation_id: {record.reservation_id}"
            )
        if record.status != ReservationStatus.PENDING:
            raise ValueError("A new reservation record must be PENDING.")
        self._records[record.reservation_id] = record

    def get(self, reservation_id: str) -> ReservationRecord:
        try:
            return self._records[reservation_id]
        except KeyError as exc:
            raise KeyError(f"Unknown reservation_id: {reservation_id}") from exc

    def activate(self, reservation_id: str, *, at: float) -> ReservationRecord:
        record = self.get(reservation_id)
        if record.status != ReservationStatus.PENDING:
            raise RuntimeError(
                f"Only PENDING reservations may activate, got {record.status.value}."
            )
        record.status = ReservationStatus.ACTIVE
        record.activated_at = float(at)
        record.expires_at = float(at) + record.duration
        return record

    def release(self, reservation_id: str, *, at: float) -> ReservationRecord:
        record = self.get(reservation_id)
        if record.status != ReservationStatus.ACTIVE:
            raise RuntimeError(
                f"Only ACTIVE reservations may release, got {record.status.value}."
            )
        record.status = ReservationStatus.RELEASED
        record.released_at = float(at)
        return record

    def expire(self, *, now: float) -> list[ReservationRecord]:
        expired: list[ReservationRecord] = []
        for record in self._records.values():
            if (
                record.status == ReservationStatus.ACTIVE
                and record.expires_at is not None
                and record.expires_at <= now
            ):
                record.status = ReservationStatus.EXPIRED
                expired.append(record)
        return expired

    @property
    def records(self) -> tuple[ReservationRecord, ...]:
        return tuple(self._records.values())

    @property
    def active_records(self) -> tuple[ReservationRecord, ...]:
        return tuple(
            record
            for record in self._records.values()
            if record.status == ReservationStatus.ACTIVE
        )


@dataclass(slots=True)
class FixedPRMACMetrics:
    """Day09 reservation-control metrics."""

    reservation_requests: int = 0
    successful_reservations: int = 0
    released_reservations: int = 0
    expired_reservations: int = 0
    control_frames_sent: int = 0
    control_bytes_sent: int = 0
    setup_delays: list[float] = field(default_factory=list)

    def record_frame(
        self,
        frame_type: PRMACFrameType,
        config: FixedPRMACConfig,
    ) -> None:
        self.control_frames_sent += 1
        sizes = {
            PRMACFrameType.PR_REQ: config.pr_req_size_bytes,
            PRMACFrameType.PR_ACK: config.pr_ack_size_bytes,
            PRMACFrameType.RELEASE: config.release_size_bytes,
        }
        self.control_bytes_sent += sizes[frame_type]

    def summary(self, table: ReservationTable) -> dict[str, int | float]:
        average_setup_delay = (
            sum(self.setup_delays) / len(self.setup_delays)
            if self.setup_delays
            else 0.0
        )
        return {
            "reservation_requests": self.reservation_requests,
            "successful_reservations": self.successful_reservations,
            "released_reservations": self.released_reservations,
            "expired_reservations": self.expired_reservations,
            "active_reservations": len(table.active_records),
            "control_frames_sent": self.control_frames_sent,
            "control_bytes_sent": self.control_bytes_sent,
            "average_setup_delay": average_setup_delay,
        }


class FixedPRMACReservationController:
    """Successful Day09 PR_REQ/PR_ACK reservation control plane."""

    PRIORITY_CONTROL_TX = 20
    PRIORITY_CONTROL_RX = 10
    PRIORITY_RESERVATION_START = 40

    def __init__(
        self,
        *,
        simulator: Simulator,
        config: FixedPRMACConfig | None = None,
        adjacency: dict[int, set[int]] | None = None,
        table: ReservationTable | None = None,
        metrics: FixedPRMACMetrics | None = None,
    ) -> None:
        self.simulator = simulator
        self.config = config or FixedPRMACConfig()
        self.adjacency = adjacency
        self.table = table or ReservationTable()
        self.metrics = metrics or FixedPRMACMetrics()

        self.frames: list[PRMACFrame] = []
        self.trace: list[ReservationTraceRecord] = []
        self._reservation_sequence = 0

    @property
    def now(self) -> float:
        return float(self.simulator.now)

    def schedule_reservation(
        self,
        packet: Packet,
        *,
        flow_id: str | None = None,
        at: float | None = None,
    ) -> str:
        """Schedule one successful fixed-length segment reservation."""
        request_time = self.now if at is None else float(at)
        if request_time < self.now:
            raise ValueError("Reservation cannot be scheduled in the past.")

        route = tuple(int(node_id) for node_id in packet.route)
        if len(route) < 2:
            raise ValueError("Fixed-PRMAC requires a path with at least one hop.")

        start_index = int(packet.current_hop_index)
        if not 0 <= start_index < len(route) - 1:
            raise ValueError(
                "Packet must have at least one remaining hop to reserve."
            )
        if int(packet.current_node) != route[start_index]:
            raise RuntimeError("Packet current node is inconsistent with route.")

        remaining_hops = len(route) - 1 - start_index
        effective_hops = min(self.config.fixed_k, remaining_hops)
        links = tuple(
            ReservedLink(route[index], route[index + 1])
            for index in range(start_index, start_index + effective_hops)
        )
        self._validate_links(links)

        resolved_flow_id = flow_id or f"flow-{packet.source}-{packet.destination}"
        self._reservation_sequence += 1
        reservation_id = (
            f"{resolved_flow_id}:packet-{packet.packet_id}:"
            f"segment-{start_index}:request-{self._reservation_sequence}"
        )
        record = ReservationRecord(
            reservation_id=reservation_id,
            flow_id=resolved_flow_id,
            packet_id=int(packet.packet_id),
            path=route,
            segment_start_index=start_index,
            requested_hops=self.config.fixed_k,
            effective_hops=effective_hops,
            reserved_links=links,
            initiator=links[0].sender,
            endpoint=links[-1].receiver,
            priority=int(packet.priority),
            duration=self.config.reservation_duration,
            requested_at=request_time,
        )
        self.table.add_pending(record)
        self.simulator.schedule_at(
            request_time,
            lambda: self._begin_reservation(record),
            event_type="RESERVATION_START",
            priority=self.PRIORITY_RESERVATION_START,
        )
        return reservation_id

    def schedule_release(
        self,
        reservation_id: str,
        *,
        at: float | None = None,
    ) -> None:
        """Propagate RELEASE along an active reservation segment."""
        release_time = self.now if at is None else float(at)
        if release_time < self.now:
            raise ValueError("RELEASE cannot be scheduled in the past.")
        record = self.table.get(reservation_id)
        if record.status != ReservationStatus.ACTIVE:
            raise RuntimeError("Only an ACTIVE reservation can send RELEASE.")

        self.simulator.schedule_at(
            release_time,
            lambda: self._transmit_release(record, 0),
            event_type="RELEASE_TX",
            priority=self.PRIORITY_CONTROL_TX,
        )

    def expire_reservations(self, *, now: float | None = None) -> list[str]:
        expiration_time = self.now if now is None else float(now)
        expired = self.table.expire(now=expiration_time)
        for record in expired:
            self.metrics.expired_reservations += 1
            self._trace(
                "RESERVATION_EXPIRED",
                record,
                node_id=record.initiator,
                detail=f"expires_at={record.expires_at:.9f}s",
            )
        return [record.reservation_id for record in expired]

    def _begin_reservation(self, record: ReservationRecord) -> None:
        if record.status != ReservationStatus.PENDING:
            return
        self.metrics.reservation_requests += 1
        self._trace(
            "RESERVATION_START",
            record,
            node_id=record.initiator,
            detail=(
                f"requested_k={record.requested_hops}, "
                f"effective_k={record.effective_hops}, "
                f"fixed_cw_min={self.config.fixed_cw_min}"
            ),
        )
        self.simulator.schedule(
            0.0,
            lambda: self._transmit_pr_req(record, 0),
            event_type="PR_REQ_TX",
            priority=self.PRIORITY_CONTROL_TX,
        )

    def _transmit_pr_req(
        self,
        record: ReservationRecord,
        link_index: int,
    ) -> None:
        link = record.reserved_links[link_index]
        frame = self._make_frame(
            PRMACFrameType.PR_REQ,
            record,
            sender=link.sender,
            receiver=link.receiver,
        )
        self._record_frame(frame)
        self._trace(
            "PR_REQ_TX",
            record,
            node_id=link.sender,
            frame_type=frame.frame_type.value,
            detail=f"{link.sender}->{link.receiver}, link_index={link_index}",
        )
        self.simulator.schedule(
            self.config.link_delay(PRMACFrameType.PR_REQ),
            lambda: self._receive_pr_req(record, link_index, frame),
            event_type="PR_REQ_RX",
            priority=self.PRIORITY_CONTROL_RX,
        )

    def _receive_pr_req(
        self,
        record: ReservationRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        link = record.reserved_links[link_index]
        self._trace(
            "PR_REQ_RX",
            record,
            node_id=link.receiver,
            frame_type=frame.frame_type.value,
            detail=f"from={link.sender}, link_index={link_index}",
        )
        if link_index + 1 < record.effective_hops:
            self.simulator.schedule(
                self.config.sifs_time,
                lambda: self._transmit_pr_req(record, link_index + 1),
                event_type="PR_REQ_TX",
                priority=self.PRIORITY_CONTROL_TX,
            )
            return

        self.simulator.schedule(
            self.config.sifs_time,
            lambda: self._transmit_pr_ack(
                record,
                record.effective_hops - 1,
            ),
            event_type="PR_ACK_TX",
            priority=self.PRIORITY_CONTROL_TX,
        )

    def _transmit_pr_ack(
        self,
        record: ReservationRecord,
        reverse_index: int,
    ) -> None:
        link = record.reserved_links[reverse_index]
        frame = self._make_frame(
            PRMACFrameType.PR_ACK,
            record,
            sender=link.receiver,
            receiver=link.sender,
            reserved_links=record.reserved_links,
        )
        self._record_frame(frame)
        self._trace(
            "PR_ACK_TX",
            record,
            node_id=link.receiver,
            frame_type=frame.frame_type.value,
            detail=f"{link.receiver}->{link.sender}, reverse_index={reverse_index}",
        )
        self.simulator.schedule(
            self.config.link_delay(PRMACFrameType.PR_ACK),
            lambda: self._receive_pr_ack(record, reverse_index, frame),
            event_type="PR_ACK_RX",
            priority=self.PRIORITY_CONTROL_RX,
        )

    def _receive_pr_ack(
        self,
        record: ReservationRecord,
        reverse_index: int,
        frame: PRMACFrame,
    ) -> None:
        link = record.reserved_links[reverse_index]
        self._trace(
            "PR_ACK_RX",
            record,
            node_id=link.sender,
            frame_type=frame.frame_type.value,
            detail=f"from={link.receiver}, reverse_index={reverse_index}",
        )
        if reverse_index > 0:
            self.simulator.schedule(
                self.config.sifs_time,
                lambda: self._transmit_pr_ack(record, reverse_index - 1),
                event_type="PR_ACK_TX",
                priority=self.PRIORITY_CONTROL_TX,
            )
            return

        activated = self.table.activate(record.reservation_id, at=self.now)
        self.metrics.successful_reservations += 1
        self.metrics.setup_delays.append(self.now - record.requested_at)
        self._trace(
            "RESERVATION_ACTIVE",
            activated,
            node_id=activated.initiator,
            detail=(
                f"endpoint={activated.endpoint}, "
                f"links={len(activated.reserved_links)}, "
                f"expires_at={activated.expires_at:.9f}s"
            ),
        )

    def _transmit_release(
        self,
        record: ReservationRecord,
        link_index: int,
    ) -> None:
        link = record.reserved_links[link_index]
        frame = self._make_frame(
            PRMACFrameType.RELEASE,
            record,
            sender=link.sender,
            receiver=link.receiver,
            reserved_links=record.reserved_links,
        )
        self._record_frame(frame)
        self._trace(
            "RELEASE_TX",
            record,
            node_id=link.sender,
            frame_type=frame.frame_type.value,
            detail=f"{link.sender}->{link.receiver}, link_index={link_index}",
        )
        self.simulator.schedule(
            self.config.link_delay(PRMACFrameType.RELEASE),
            lambda: self._receive_release(record, link_index, frame),
            event_type="RELEASE_RX",
            priority=self.PRIORITY_CONTROL_RX,
        )

    def _receive_release(
        self,
        record: ReservationRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        link = record.reserved_links[link_index]
        self._trace(
            "RELEASE_RX",
            record,
            node_id=link.receiver,
            frame_type=frame.frame_type.value,
            detail=f"from={link.sender}, link_index={link_index}",
        )
        if link_index + 1 < record.effective_hops:
            self.simulator.schedule(
                self.config.sifs_time,
                lambda: self._transmit_release(record, link_index + 1),
                event_type="RELEASE_TX",
                priority=self.PRIORITY_CONTROL_TX,
            )
            return

        released = self.table.release(record.reservation_id, at=self.now)
        self.metrics.released_reservations += 1
        self._trace(
            "RESERVATION_RELEASED",
            released,
            node_id=released.endpoint,
            detail=f"released_at={released.released_at:.9f}s",
        )

    def _make_frame(
        self,
        frame_type: PRMACFrameType,
        record: ReservationRecord,
        *,
        sender: int,
        receiver: int,
        reserved_links: tuple[ReservedLink, ...] = (),
    ) -> PRMACFrame:
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
            reserved_links=reserved_links,
        )

    def _record_frame(self, frame: PRMACFrame) -> None:
        self.frames.append(frame)
        self.metrics.record_frame(frame.frame_type, self.config)

    def _trace(
        self,
        event: str,
        record: ReservationRecord,
        *,
        node_id: int,
        frame_type: str = "",
        detail: str = "",
    ) -> None:
        self.trace.append(
            ReservationTraceRecord(
                time=self.now,
                event=event,
                node_id=int(node_id),
                packet_id=record.packet_id,
                reservation_id=record.reservation_id,
                frame_type=frame_type,
                detail=detail,
            )
        )

    def _validate_links(self, links: tuple[ReservedLink, ...]) -> None:
        if self.adjacency is None:
            return
        for link in links:
            if link.receiver not in self.adjacency.get(link.sender, set()):
                raise ValueError(
                    f"Route edge {link.sender}->{link.receiver} "
                    "is not a configured neighbor link."
                )

    def export_trace_csv(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(ReservationTraceRecord.__dataclass_fields__.keys())
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.trace:
                writer.writerow(asdict(record))
        return destination

    def export_summary_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": asdict(self.config),
            "metrics": self.metrics.summary(self.table),
            "reservations": [
                {
                    **asdict(record),
                    "status": record.status.value,
                    "reserved_links": [
                        asdict(link) for link in record.reserved_links
                    ],
                }
                for record in self.table.records
            ],
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination


__all__ = [
    "FixedPRMACConfig",
    "FixedPRMACMetrics",
    "FixedPRMACReservationController",
    "ReservationTable",
]
