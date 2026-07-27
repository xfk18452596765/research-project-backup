"""Day13 complete end-to-end Fixed-PRMAC orchestration.

Scope:
- DIFS + fixed-CW initial access for every path-reservation segment;
- Day12 PR_NACK/BEB retry sequence for each segment;
- Day11 DATA/H_ACK forwarding after reservation success;
- RELEASE before the next segment;
- repeat until the destination is reached or one segment exhausts retries.

This file deliberately contains no Q-learning or adaptive K/CW policy.
"""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY12_CODE = DAILY_DIR / "Day12_Fixed-PRMAC失败与重传" / "code"
DAY11_CODE = DAILY_DIR / "Day11_Fixed-PRMAC连续转发" / "code"
DAY10_CODE = DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

# Current-day compatible messages must remain first. Day12 then imports the
# Day13-compatible ReservationRecord instead of an older lifecycle model.
_import_paths = [CURRENT_DIR, DAY12_CODE, DAY11_CODE, DAY10_CODE, DAY09_CODE, DAY03_CODE]
for path in _import_paths:
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from fixed_prmac_messages import PRMACFrame, ReservationRecord, ReservationStatus  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_forwarding import (  # type: ignore  # noqa: E402
    SegmentForwardingRecord,
    SegmentForwardingStatus,
)
from fixed_prmac_retry import (  # type: ignore  # noqa: E402
    Day12FixedPRMACConfig,
    Day12FixedPRMACMetrics,
    Day12ReservationTable,
    FixedPRMACRetryController,
    ReservationRetryRecord,
    ReservationRetryStatus,
)


class EndToEndStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EndToEndSegmentStatus(str, Enum):
    QUEUED = "QUEUED"
    ACCESS_BACKOFF = "ACCESS_BACKOFF"
    RESERVING = "RESERVING"
    FORWARDING = "FORWARDING"
    RELEASING = "RELEASING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(slots=True)
class EndToEndSegmentRecord:
    segment_number: int
    segment_start_index: int
    scheduled_at: float
    access_cw: int = 0
    access_backoff_slots: int = 0
    access_delay: float = 0.0
    status: EndToEndSegmentStatus = EndToEndSegmentStatus.QUEUED
    queue_enqueued_at: float | None = None
    queue_service_started_at: float | None = None
    queue_delay: float = 0.0
    access_completed_at: float | None = None
    retry_id: str | None = None
    reservation_id: str | None = None
    transfer_id: str | None = None
    effective_hops: int | None = None
    retries_used: int = 0
    reservation_succeeded_at: float | None = None
    forwarding_completed_at: float | None = None
    released_at: float | None = None
    failure_reason: str = ""


@dataclass(slots=True)
class EndToEndRecord:
    session_id: str
    flow_id: str
    packet_id: int
    route: tuple[int, ...]
    scheduled_at: float
    status: EndToEndStatus = EndToEndStatus.SCHEDULED
    started_at: float | None = None
    completed_at: float | None = None
    failure_reason: str = ""
    segments: list[EndToEndSegmentRecord] = field(default_factory=list)

    @property
    def completion_delay(self) -> float | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return self.completed_at - self.started_at

    @property
    def completed_segments(self) -> int:
        return sum(segment.status == EndToEndSegmentStatus.COMPLETED for segment in self.segments)

    @property
    def total_retries(self) -> int:
        return sum(segment.retries_used for segment in self.segments)


@dataclass(frozen=True, slots=True)
class EndToEndTraceRecord:
    time: float
    event: str
    node_id: int
    packet_id: int
    session_id: str
    segment_number: int
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Day13FixedPRMACConfig(Day12FixedPRMACConfig):
    """Day12 parameters plus explicit initial access and local FIFO queues."""

    initial_access_enabled: bool = True
    queue_limit: int = 200

    def __post_init__(self) -> None:
        Day12FixedPRMACConfig.__post_init__(self)
        if self.queue_limit <= 0:
            raise ValueError("queue_limit must be positive.")

    def initial_access_delay(self, backoff_slots: int) -> float:
        if backoff_slots < 0:
            raise ValueError("backoff_slots cannot be negative.")
        if not self.initial_access_enabled:
            return 0.0
        return self.difs_time + backoff_slots * self.slot_time


@dataclass(slots=True)
class Day13FixedPRMACMetrics(Day12FixedPRMACMetrics):
    end_to_end_sessions_started: int = 0
    end_to_end_packets_delivered: int = 0
    end_to_end_packets_dropped: int = 0
    end_to_end_segments_started: int = 0
    segment_queue_entries: int = 0
    queue_overflow_drops: int = 0
    maximum_segment_queue_length: int = 0
    segment_queue_delays: list[float] = field(default_factory=list)
    initial_access_backoff_slots: int = 0
    initial_access_delays: list[float] = field(default_factory=list)
    end_to_end_delays: list[float] = field(default_factory=list)

    def summary(self, table: Day12ReservationTable) -> dict[str, int | float]:
        payload = Day12FixedPRMACMetrics.summary(self, table)
        delivered = self.end_to_end_packets_delivered
        started = self.end_to_end_sessions_started
        payload.update(
            {
                "end_to_end_sessions_started": started,
                "end_to_end_packets_delivered": delivered,
                "end_to_end_packets_dropped": self.end_to_end_packets_dropped,
                "end_to_end_delivery_ratio": delivered / started if started else 0.0,
                "end_to_end_segments_started": self.end_to_end_segments_started,
                "segment_queue_entries": self.segment_queue_entries,
                "queue_overflow_drops": self.queue_overflow_drops,
                "maximum_segment_queue_length": self.maximum_segment_queue_length,
                "total_segment_queue_delay": sum(self.segment_queue_delays),
                "average_segment_queue_delay": _mean(self.segment_queue_delays),
                "maximum_segment_queue_delay": max(self.segment_queue_delays, default=0.0),
                "initial_access_attempts": len(self.initial_access_delays),
                "total_initial_access_backoff_slots": self.initial_access_backoff_slots,
                "total_initial_access_delay": sum(self.initial_access_delays),
                "average_initial_access_delay": _mean(self.initial_access_delays),
                "average_end_to_end_delay": _mean(self.end_to_end_delays),
                "p95_end_to_end_delay": _percentile(self.end_to_end_delays, 0.95),
                "p99_end_to_end_delay": _percentile(self.end_to_end_delays, 0.99),
            }
        )
        return payload


class FixedPRMACEndToEndController(FixedPRMACRetryController):
    """Compose Day09-Day12 primitives into complete multi-segment delivery."""

    PRIORITY_END_TO_END_START = 40
    PRIORITY_SEGMENT_ACCESS_COMPLETE = 40

    def __init__(
        self,
        *,
        simulator: Simulator,
        config: Day13FixedPRMACConfig | None = None,
        adjacency: dict[int, set[int]] | None = None,
        table: Day12ReservationTable | None = None,
        metrics: Day13FixedPRMACMetrics | None = None,
    ) -> None:
        resolved_config = config or Day13FixedPRMACConfig()
        resolved_table = table or Day12ReservationTable()
        resolved_metrics = metrics or Day13FixedPRMACMetrics()
        super().__init__(
            simulator=simulator,
            config=resolved_config,
            adjacency=adjacency,
            table=resolved_table,
            metrics=resolved_metrics,
        )
        self.end_to_end_records: dict[str, EndToEndRecord] = {}
        self.end_to_end_trace: list[EndToEndTraceRecord] = []
        self._session_packets: dict[str, Packet] = {}
        self._packet_to_session: dict[int, str] = {}
        self._retry_to_segment: dict[str, tuple[str, int]] = {}
        self._reservation_to_segment: dict[str, tuple[str, int]] = {}
        self._transfer_to_segment: dict[str, tuple[str, int]] = {}
        self._processed_retry_success: set[str] = set()
        self._processed_forward_complete: set[str] = set()
        self._processed_release: set[str] = set()
        self._segment_queues: dict[int, deque[tuple[str, int]]] = {}
        self._active_segment_by_node: dict[int, tuple[str, int]] = {}
        self._session_sequence = 0
        self._access_rng = random.Random(resolved_config.random_seed + 13_013)

    @property
    def config(self) -> Day13FixedPRMACConfig:
        return self._config

    @config.setter
    def config(self, value: Day13FixedPRMACConfig) -> None:
        self._config = value

    @property
    def metrics(self) -> Day13FixedPRMACMetrics:
        return self._metrics

    @metrics.setter
    def metrics(self, value: Day13FixedPRMACMetrics) -> None:
        self._metrics = value

    def schedule_end_to_end(
        self,
        packet: Packet,
        *,
        flow_id: str | None = None,
        at: float | None = None,
    ) -> str:
        start_time = self.now if at is None else float(at)
        if start_time < self.now:
            raise ValueError("End-to-end session cannot be scheduled in the past.")
        self._validate_end_to_end_packet(packet)
        if int(packet.packet_id) in self._packet_to_session:
            raise RuntimeError("An end-to-end session already exists for this packet.")

        resolved_flow = flow_id or f"flow-{packet.source}-{packet.destination}"
        self._session_sequence += 1
        session_id = (
            f"{resolved_flow}:packet-{packet.packet_id}:"
            f"end-to-end-{self._session_sequence}"
        )
        record = EndToEndRecord(
            session_id=session_id,
            flow_id=resolved_flow,
            packet_id=int(packet.packet_id),
            route=tuple(int(node) for node in packet.route),
            scheduled_at=start_time,
        )
        self.end_to_end_records[session_id] = record
        self._session_packets[session_id] = packet
        self._packet_to_session[int(packet.packet_id)] = session_id
        self.simulator.schedule_at(
            start_time,
            lambda: self._begin_end_to_end(record, packet),
            event_type="END_TO_END_START",
            priority=self.PRIORITY_END_TO_END_START,
        )
        return session_id

    def _validate_end_to_end_packet(self, packet: Packet) -> None:
        route = tuple(int(node) for node in packet.route)
        if len(route) < 2:
            raise ValueError("End-to-end Fixed-PRMAC requires at least one hop.")
        if int(packet.current_hop_index) != 0 or int(packet.current_node) != int(packet.source):
            raise ValueError("A new end-to-end session must start at the route source.")
        if packet.status in {PacketStatus.DROPPED, PacketStatus.DELIVERED}:
            raise RuntimeError("A terminal packet cannot start another end-to-end session.")

    def _begin_end_to_end(self, record: EndToEndRecord, packet: Packet) -> None:
        if record.status != EndToEndStatus.SCHEDULED:
            return
        record.status = EndToEndStatus.IN_PROGRESS
        record.started_at = self.now
        self.metrics.end_to_end_sessions_started += 1
        self._trace_e2e("END_TO_END_START", record, packet, segment_number=0)
        self._schedule_next_segment(record, packet)

    def _schedule_next_segment(self, record: EndToEndRecord, packet: Packet) -> None:
        """Enqueue the next reservation segment at its local start node.

        The queue includes the active head item, matching the Day08 DCF node queue:
        only the head may begin DIFS/backoff; later local packets wait without
        generating PR_NACK or consuming reservation retries.
        """
        if record.status != EndToEndStatus.IN_PROGRESS:
            return
        if packet.status == PacketStatus.DELIVERED or packet.remaining_hops == 0:
            self._complete_end_to_end(record, packet)
            return

        segment_number = len(record.segments) + 1
        node_id = int(packet.current_node)
        segment = EndToEndSegmentRecord(
            segment_number=segment_number,
            segment_start_index=int(packet.current_hop_index),
            scheduled_at=self.now,
            queue_enqueued_at=self.now,
        )
        record.segments.append(segment)
        self.metrics.end_to_end_segments_started += 1

        queue = self._segment_queues.setdefault(node_id, deque())
        if len(queue) >= self.config.queue_limit:
            reason = (
                f"segment_queue_overflow: node={node_id}, "
                f"queue_limit={self.config.queue_limit}"
            )
            segment.status = EndToEndSegmentStatus.FAILED
            segment.failure_reason = reason
            self.metrics.queue_overflow_drops += 1
            self._trace_e2e(
                "SEGMENT_QUEUE_OVERFLOW",
                record,
                packet,
                segment_number=segment_number,
                detail=reason,
            )
            self._fail_end_to_end(record, packet, reason)
            return

        mapping = (record.session_id, segment_number - 1)
        queue.append(mapping)
        self.metrics.segment_queue_entries += 1
        self.metrics.maximum_segment_queue_length = max(
            self.metrics.maximum_segment_queue_length,
            len(queue),
        )
        self._trace_e2e(
            "SEGMENT_QUEUE_ENQUEUE",
            record,
            packet,
            segment_number=segment_number,
            detail=(
                f"segment_start_index={segment.segment_start_index}, "
                f"queue_length={len(queue)}, queue_limit={self.config.queue_limit}"
            ),
        )
        self._try_start_node_queue(node_id)

    def _try_start_node_queue(self, node_id: int) -> None:
        if node_id in self._active_segment_by_node:
            return
        queue = self._segment_queues.get(node_id)
        if not queue:
            return

        mapping = queue[0]
        session_id, segment_index = mapping
        record = self.end_to_end_records[session_id]
        packet = self._session_packets[session_id]
        segment = record.segments[segment_index]
        if record.status != EndToEndStatus.IN_PROGRESS:
            queue.popleft()
            self._try_start_node_queue(node_id)
            return
        if int(packet.current_node) != node_id:
            raise RuntimeError("Queued packet is not located at its segment start node.")
        if int(packet.current_hop_index) != segment.segment_start_index:
            raise RuntimeError("Queued packet hop index changed before local service.")

        self._active_segment_by_node[node_id] = mapping
        segment.queue_service_started_at = self.now
        enqueued_at = segment.queue_enqueued_at
        if enqueued_at is None:
            raise RuntimeError("Queued segment must expose queue_enqueued_at.")
        segment.queue_delay = self.now - enqueued_at
        self.metrics.segment_queue_delays.append(segment.queue_delay)

        backoff_slots = self._access_rng.randint(0, self.config.fixed_cw_min)
        access_delay = self.config.initial_access_delay(backoff_slots)
        segment.access_cw = self.config.fixed_cw_min
        segment.access_backoff_slots = backoff_slots
        segment.access_delay = access_delay
        segment.status = EndToEndSegmentStatus.ACCESS_BACKOFF
        self.metrics.initial_access_backoff_slots += backoff_slots
        self.metrics.initial_access_delays.append(access_delay)
        self._trace_e2e(
            "SEGMENT_ACCESS_BACKOFF",
            record,
            packet,
            segment_number=segment.segment_number,
            detail=(
                f"segment_start_index={segment.segment_start_index}, "
                f"queue_delay={segment.queue_delay:.9f}s, "
                f"cw={segment.access_cw}, backoff_slots={backoff_slots}, "
                f"access_delay={access_delay:.9f}s"
            ),
        )
        self.simulator.schedule(
            access_delay,
            lambda: self._start_segment_retry(record, packet, segment),
            event_type="SEGMENT_ACCESS_COMPLETE",
            priority=self.PRIORITY_SEGMENT_ACCESS_COMPLETE,
        )

    def _finish_node_queue_service(
        self,
        node_id: int,
        mapping: tuple[str, int],
    ) -> None:
        active = self._active_segment_by_node.get(node_id)
        if active != mapping:
            raise RuntimeError("Finished segment is not the active local queue head.")
        queue = self._segment_queues.get(node_id)
        if not queue or queue[0] != mapping:
            raise RuntimeError("Local FIFO head changed during segment service.")
        queue.popleft()
        del self._active_segment_by_node[node_id]
        if not queue:
            self._segment_queues.pop(node_id, None)
        self._try_start_node_queue(node_id)

    def _start_segment_retry(
        self,
        record: EndToEndRecord,
        packet: Packet,
        segment: EndToEndSegmentRecord,
    ) -> None:
        if record.status != EndToEndStatus.IN_PROGRESS:
            return
        if packet.current_hop_index != segment.segment_start_index:
            raise RuntimeError("Packet moved before its segment access completed.")
        segment.access_completed_at = self.now
        segment.status = EndToEndSegmentStatus.RESERVING
        retry_id = self.schedule_reservation_with_retry(
            packet,
            flow_id=record.flow_id,
            at=self.now,
        )
        segment.retry_id = retry_id
        self._retry_to_segment[retry_id] = (record.session_id, segment.segment_number - 1)
        self._trace_e2e(
            "SEGMENT_RESERVATION_START",
            record,
            packet,
            segment_number=segment.segment_number,
            detail=f"retry_id={retry_id}",
        )

    def _receive_pr_ack(
        self,
        reservation: ReservationRecord,
        reverse_index: int,
        frame: PRMACFrame,
    ) -> None:
        super()._receive_pr_ack(reservation, reverse_index, frame)
        retry_id = self._reservation_to_retry_id.get(reservation.reservation_id)
        if retry_id is None or retry_id in self._processed_retry_success:
            return
        retry = self.retry_records[retry_id]
        if retry.status != ReservationRetryStatus.SUCCEEDED:
            return
        mapping = self._retry_to_segment.get(retry_id)
        if mapping is None:
            return

        self._processed_retry_success.add(retry_id)
        session_id, segment_index = mapping
        e2e = self.end_to_end_records[session_id]
        packet = self._session_packets[session_id]
        segment = e2e.segments[segment_index]
        segment.reservation_id = reservation.reservation_id
        segment.effective_hops = reservation.effective_hops
        segment.retries_used = retry.retries_used
        segment.reservation_succeeded_at = self.now
        segment.status = EndToEndSegmentStatus.FORWARDING
        self._reservation_to_segment[reservation.reservation_id] = mapping
        transfer_id = self.schedule_reserved_forwarding(
            reservation.reservation_id,
            packet,
            at=self.now,
        )
        segment.transfer_id = transfer_id
        self._transfer_to_segment[transfer_id] = mapping
        self._trace_e2e(
            "SEGMENT_RESERVATION_ACTIVE",
            e2e,
            packet,
            segment_number=segment.segment_number,
            detail=(
                f"reservation_id={reservation.reservation_id}, "
                f"effective_hops={reservation.effective_hops}, "
                f"retries_used={retry.retries_used}"
            ),
        )

    def _receive_h_ack(
        self,
        reservation: ReservationRecord,
        packet: Packet,
        forwarding: SegmentForwardingRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        super()._receive_h_ack(reservation, packet, forwarding, link_index, frame)
        if forwarding.status != SegmentForwardingStatus.COMPLETED:
            return
        if forwarding.transfer_id in self._processed_forward_complete:
            return
        mapping = self._transfer_to_segment.get(forwarding.transfer_id)
        if mapping is None:
            return

        self._processed_forward_complete.add(forwarding.transfer_id)
        session_id, segment_index = mapping
        e2e = self.end_to_end_records[session_id]
        segment = e2e.segments[segment_index]
        segment.forwarding_completed_at = self.now
        segment.status = EndToEndSegmentStatus.RELEASING

        # DCF records delivery at ACK reception. Day11 records it at DATA_RX.
        # Day13 aligns the comparison boundary at the final H_ACK reception.
        if packet.status == PacketStatus.DELIVERED:
            packet.delivered_at = self.now
            self._complete_end_to_end(e2e, packet)

        self._trace_e2e(
            "SEGMENT_FORWARD_COMPLETE",
            e2e,
            packet,
            segment_number=segment.segment_number,
            detail=(
                f"reservation_id={reservation.reservation_id}, "
                f"packet_node={packet.current_node}, "
                f"packet_status={packet.status.value}"
            ),
        )
        self.schedule_release(reservation.reservation_id, at=self.now)

    def _receive_release(
        self,
        reservation: ReservationRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        super()._receive_release(reservation, link_index, frame)
        if reservation.status != ReservationStatus.RELEASED:
            return
        if reservation.reservation_id in self._processed_release:
            return
        mapping = self._reservation_to_segment.get(reservation.reservation_id)
        if mapping is None:
            return

        self._processed_release.add(reservation.reservation_id)
        session_id, segment_index = mapping
        e2e = self.end_to_end_records[session_id]
        packet = self._session_packets[session_id]
        segment = e2e.segments[segment_index]
        segment.released_at = self.now
        segment.status = EndToEndSegmentStatus.COMPLETED
        self._trace_e2e(
            "SEGMENT_RELEASE_COMPLETE",
            e2e,
            packet,
            segment_number=segment.segment_number,
            detail=f"reservation_id={reservation.reservation_id}",
        )
        start_node = int(e2e.route[segment.segment_start_index])
        self._finish_node_queue_service(start_node, mapping)
        if e2e.status == EndToEndStatus.IN_PROGRESS:
            self._schedule_next_segment(e2e, packet)

    def _handle_rejected_attempt(
        self,
        retry_record: ReservationRetryRecord,
        *,
        packet: Packet,
        record: ReservationRecord,
    ) -> None:
        super()._handle_rejected_attempt(retry_record, packet=packet, record=record)
        if retry_record.status != ReservationRetryStatus.FAILED:
            return
        mapping = self._retry_to_segment.get(retry_record.retry_id)
        if mapping is None:
            return
        session_id, segment_index = mapping
        e2e = self.end_to_end_records[session_id]
        segment = e2e.segments[segment_index]
        segment.status = EndToEndSegmentStatus.FAILED
        segment.retries_used = retry_record.retries_used
        segment.failure_reason = retry_record.failure_reason
        self._fail_end_to_end(e2e, packet, retry_record.failure_reason)
        start_node = int(e2e.route[segment.segment_start_index])
        self._finish_node_queue_service(start_node, mapping)

    def _complete_end_to_end(self, record: EndToEndRecord, packet: Packet) -> None:
        if record.status == EndToEndStatus.COMPLETED:
            return
        if packet.status != PacketStatus.DELIVERED:
            raise RuntimeError("End-to-end completion requires a DELIVERED packet.")
        record.status = EndToEndStatus.COMPLETED
        record.completed_at = self.now
        if packet.delivered_at is None:
            packet.delivered_at = self.now
        delay = packet.end_to_end_delay
        if delay is None:
            raise RuntimeError("Delivered packet must expose end-to-end delay.")
        self.metrics.end_to_end_packets_delivered += 1
        self.metrics.end_to_end_delays.append(float(delay))
        self._trace_e2e(
            "END_TO_END_COMPLETE",
            record,
            packet,
            segment_number=len(record.segments),
            detail=(
                f"segments={len(record.segments)}, total_retries={record.total_retries}, "
                f"end_to_end_delay={delay:.9f}s"
            ),
        )

    def _fail_end_to_end(
        self,
        record: EndToEndRecord,
        packet: Packet,
        reason: str,
    ) -> None:
        if record.status == EndToEndStatus.FAILED:
            return
        record.status = EndToEndStatus.FAILED
        record.completed_at = self.now
        record.failure_reason = reason
        packet.status = PacketStatus.DROPPED
        self.metrics.end_to_end_packets_dropped += 1
        self._trace_e2e(
            "END_TO_END_FAILED",
            record,
            packet,
            segment_number=len(record.segments),
            detail=reason,
        )

    def _trace_e2e(
        self,
        event: str,
        record: EndToEndRecord,
        packet: Packet,
        *,
        segment_number: int,
        detail: str = "",
    ) -> None:
        self.end_to_end_trace.append(
            EndToEndTraceRecord(
                time=self.now,
                event=event,
                node_id=int(packet.current_node),
                packet_id=int(packet.packet_id),
                session_id=record.session_id,
                segment_number=int(segment_number),
                detail=detail,
            )
        )

    def segment_queue_snapshot(self) -> dict[int, list[dict[str, int | str]]]:
        snapshot: dict[int, list[dict[str, int | str]]] = {}
        for node_id, queue in self._segment_queues.items():
            snapshot[node_id] = [
                {"session_id": session_id, "segment_index": segment_index}
                for session_id, segment_index in queue
            ]
        return snapshot

    def end_to_end_snapshot(self) -> list[dict[str, object]]:
        snapshot: list[dict[str, object]] = []
        for record in self.end_to_end_records.values():
            item = asdict(record)
            item["status"] = record.status.value
            item["completion_delay"] = record.completion_delay
            segments: list[dict[str, object]] = []
            for segment in record.segments:
                segment_item = asdict(segment)
                segment_item["status"] = segment.status.value
                segments.append(segment_item)
            item["segments"] = segments
            snapshot.append(item)
        return snapshot

    def export_end_to_end_trace_csv(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fields = list(EndToEndTraceRecord.__dataclass_fields__.keys())
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in self.end_to_end_trace:
                writer.writerow(asdict(row))
        return destination

    def export_end_to_end_summary_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": asdict(self.config),
            "metrics": self.metrics.summary(self.table),
            "end_to_end_sessions": self.end_to_end_snapshot(),
            "segment_queues": self.segment_queue_snapshot(),
            "retry_sequences": self.retry_snapshot(),
            "forwardings": self.forwarding_snapshot(),
            "reservations": self.conflict_snapshot(),
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination


def _mean(values: Iterable[float]) -> float:
    data = [float(value) for value in values]
    return sum(data) / len(data) if data else 0.0


def _percentile(values: Iterable[float], probability: float) -> float:
    data = sorted(float(value) for value in values)
    if not data:
        return 0.0
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1].")
    if len(data) == 1:
        return data[0]
    position = probability * (len(data) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return data[lower]
    return data[lower] + (position - lower) * (data[upper] - data[lower])


__all__ = [
    "Day13FixedPRMACConfig",
    "Day13FixedPRMACMetrics",
    "EndToEndRecord",
    "EndToEndSegmentRecord",
    "EndToEndSegmentStatus",
    "EndToEndStatus",
    "EndToEndTraceRecord",
    "FixedPRMACEndToEndController",
]
