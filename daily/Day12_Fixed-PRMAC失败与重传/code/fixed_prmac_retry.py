"""Day12 Fixed-PRMAC reservation failure, backoff, and retry.

Scope is deliberately limited to reservation-control recovery after PR_NACK:

initial reservation attempt
→ PR_NACK / REJECTED
→ DIFS + binary-exponential random backoff
→ create a fresh reservation attempt
→ ACTIVE on success, or FAILED after retry-limit exhaustion

The implementation preserves every attempt as a separate reservation record so
conflict history and control overhead remain auditable. It inherits Day11 DATA /
H_ACK forwarding, but does not add cross-segment end-to-end forwarding, traffic
load experiments, the Day13 stop-loss comparison, or reinforcement learning.
"""
from __future__ import annotations

import json
import random
import sys
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY11_CODE = DAILY_DIR / "Day11_Fixed-PRMAC连续转发" / "code"
DAY10_CODE = DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

# Day12 must be first so Day11/Day10/Day09 import the Day12-compatible
# ReservationRecord, including the final ``failed_at`` timestamp.
_import_paths = [CURRENT_DIR, DAY11_CODE, DAY10_CODE, DAY09_CODE, DAY03_CODE]
for path in _import_paths:
    path_text = str(path)
    while path_text in sys.path:
        sys.path.remove(path_text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_messages import (  # noqa: E402
    PRMACFrame,
    ReservationRecord,
    ReservationStatus,
)
from fixed_prmac_conflict import (  # type: ignore  # noqa: E402
    ReservationConflictPolicy,
)
from fixed_prmac_forwarding import (  # type: ignore  # noqa: E402
    Day11FixedPRMACConfig,
    Day11FixedPRMACMetrics,
    FixedPRMACForwardingController,
)
from fixed_prmac_conflict import Day10ReservationTable  # type: ignore  # noqa: E402


@dataclass(frozen=True, slots=True)
class Day12FixedPRMACConfig(Day11FixedPRMACConfig):
    """Day11 configuration plus DCF-aligned reservation retry parameters.

    The defaults match the existing DCF baseline:
    - slot_time = 20 us
    - DIFS = 50 us
    - CWmin = 15 (inherited ``fixed_cw_min``)
    - CWmax = 1023
    - retry_limit = 7
    - deterministic random seed = 7

    Day12 applies these parameters only after a PR_NACK. The initial
    ``schedule_reservation`` access opportunity remains the inherited Day09
    abstraction and will be coupled to full contention in Day13.
    """

    slot_time: float = 20e-6
    difs_time: float = 50e-6
    cw_max: int = 1023
    retry_limit: int = 7
    random_seed: int = 7

    def __post_init__(self) -> None:
        Day11FixedPRMACConfig.__post_init__(self)
        if self.slot_time < 0 or self.difs_time < 0:
            raise ValueError("slot_time and difs_time cannot be negative.")
        if self.cw_max < self.fixed_cw_min:
            raise ValueError("cw_max must be at least fixed_cw_min.")
        if self.retry_limit < 0:
            raise ValueError("retry_limit cannot be negative.")

    def contention_window_for_retry(self, retry_number: int) -> int:
        """Return BEB CW for retry_number=1,2,... after the initial failure."""
        if retry_number <= 0:
            raise ValueError("retry_number must be positive.")
        expanded = (self.fixed_cw_min + 1) * (2**retry_number) - 1
        return min(expanded, self.cw_max)

    def retry_backoff_delay(self, backoff_slots: int) -> float:
        if backoff_slots < 0:
            raise ValueError("backoff_slots cannot be negative.")
        return self.difs_time + backoff_slots * self.slot_time


class ReservationRetryStatus(str, Enum):
    """Lifecycle of one packet-segment retry sequence."""

    SCHEDULED = "SCHEDULED"
    ATTEMPTING = "ATTEMPTING"
    BACKING_OFF = "BACKING_OFF"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(slots=True)
class ReservationRetryAttempt:
    """One concrete reservation request inside a retry sequence."""

    attempt_number: int
    reservation_id: str
    contention_window: int
    scheduled_at: float
    backoff_slots_before_attempt: int | None = None
    backoff_delay_before_attempt: float = 0.0
    status: ReservationStatus = ReservationStatus.PENDING
    completed_at: float | None = None
    failure_reason: str = ""


@dataclass(slots=True)
class ReservationRetryRecord:
    """Parent state joining all attempts for one packet and one segment."""

    retry_id: str
    flow_id: str
    packet_id: int
    path: tuple[int, ...]
    segment_start_index: int
    scheduled_at: float
    retry_limit: int
    status: ReservationRetryStatus = ReservationRetryStatus.SCHEDULED
    started_at: float | None = None
    succeeded_at: float | None = None
    failed_at: float | None = None
    successful_reservation_id: str | None = None
    failure_reason: str = ""
    attempts: list[ReservationRetryAttempt] = field(default_factory=list)

    @property
    def total_attempts(self) -> int:
        return len(self.attempts)

    @property
    def retries_used(self) -> int:
        return max(0, self.total_attempts - 1)

    @property
    def completion_delay(self) -> float | None:
        if self.started_at is None:
            return None
        terminal_at = self.succeeded_at if self.succeeded_at is not None else self.failed_at
        if terminal_at is None:
            return None
        return terminal_at - self.started_at


class Day12ReservationTable(Day10ReservationTable):
    """Day10 table plus REJECTED→FAILED on retry exhaustion."""

    def fail_exhausted(
        self,
        reservation_id: str,
        *,
        at: float,
        reason: str,
    ) -> ReservationRecord:
        record = self.get(reservation_id)
        if record.status != ReservationStatus.REJECTED:
            raise RuntimeError(
                "Only a REJECTED reservation may become FAILED, "
                f"got {record.status.value}."
            )
        record.status = ReservationStatus.FAILED
        record.failed_at = float(at)
        record.failure_reason = reason
        return record


@dataclass(slots=True)
class Day12FixedPRMACMetrics(Day11FixedPRMACMetrics):
    """Day11 metrics plus reservation retry/backoff measurements."""

    retry_sequences_started: int = 0
    retry_attempts_scheduled: int = 0
    reservation_retries_scheduled: int = 0
    first_attempt_successes: int = 0
    retry_successes: int = 0
    retry_exhausted_failures: int = 0
    total_retry_backoff_slots: int = 0
    retry_backoff_delays: list[float] = field(default_factory=list)
    retry_completion_delays: list[float] = field(default_factory=list)

    def summary(self, table: Day12ReservationTable) -> dict[str, int | float]:
        payload = Day11FixedPRMACMetrics.summary(self, table)
        total_backoff_delay = sum(self.retry_backoff_delays)
        average_backoff_delay = (
            total_backoff_delay / len(self.retry_backoff_delays)
            if self.retry_backoff_delays
            else 0.0
        )
        average_retries = (
            self.reservation_retries_scheduled / self.retry_sequences_started
            if self.retry_sequences_started
            else 0.0
        )
        successful_sequences = self.first_attempt_successes + self.retry_successes
        retry_sequence_success_rate = (
            successful_sequences / self.retry_sequences_started
            if self.retry_sequences_started
            else 0.0
        )
        average_completion_delay = (
            sum(self.retry_completion_delays) / len(self.retry_completion_delays)
            if self.retry_completion_delays
            else 0.0
        )
        payload.update(
            {
                "retry_sequences_started": self.retry_sequences_started,
                "retry_attempts_scheduled": self.retry_attempts_scheduled,
                "reservation_retries_scheduled": self.reservation_retries_scheduled,
                "first_attempt_successes": self.first_attempt_successes,
                "retry_successes": self.retry_successes,
                "retry_exhausted_failures": self.retry_exhausted_failures,
                "total_retry_backoff_slots": self.total_retry_backoff_slots,
                "total_retry_backoff_delay": total_backoff_delay,
                "average_retry_backoff_delay": average_backoff_delay,
                "average_retries_per_sequence": average_retries,
                "retry_sequence_success_rate": retry_sequence_success_rate,
                "average_retry_sequence_completion_delay": average_completion_delay,
            }
        )
        return payload


class FixedPRMACRetryController(FixedPRMACForwardingController):
    """Day11 controller extended only with Day12 reservation retry recovery."""

    PRIORITY_RETRY_SEQUENCE_START = 40
    PRIORITY_RETRY_ATTEMPT_START = 40

    def __init__(
        self,
        *,
        simulator: Simulator,
        config: Day12FixedPRMACConfig | None = None,
        adjacency: dict[int, set[int]] | None = None,
        table: Day12ReservationTable | None = None,
        metrics: Day12FixedPRMACMetrics | None = None,
        conflict_policy: ReservationConflictPolicy | None = None,
    ) -> None:
        resolved_config = config or Day12FixedPRMACConfig()
        resolved_table = table or Day12ReservationTable()
        resolved_metrics = metrics or Day12FixedPRMACMetrics()
        super().__init__(
            simulator=simulator,
            config=resolved_config,
            adjacency=adjacency,
            table=resolved_table,
            metrics=resolved_metrics,
            conflict_policy=conflict_policy,
        )
        self.retry_records: dict[str, ReservationRetryRecord] = {}
        self._retry_packets: dict[str, Packet] = {}
        self._reservation_to_retry_id: dict[str, str] = {}
        self._attempt_by_reservation_id: dict[str, ReservationRetryAttempt] = {}
        self._retry_key_to_id: dict[tuple[str, int, int], str] = {}
        self._retry_sequence = 0
        self._rng = random.Random(resolved_config.random_seed)

    @property
    def config(self) -> Day12FixedPRMACConfig:
        return self._config

    @config.setter
    def config(self, value: Day12FixedPRMACConfig) -> None:
        self._config = value

    @property
    def table(self) -> Day12ReservationTable:
        return self._table

    @table.setter
    def table(self, value: Day12ReservationTable) -> None:
        self._table = value

    @property
    def metrics(self) -> Day12FixedPRMACMetrics:
        return self._metrics

    @metrics.setter
    def metrics(self, value: Day12FixedPRMACMetrics) -> None:
        self._metrics = value

    def schedule_reservation_with_retry(
        self,
        packet: Packet,
        *,
        flow_id: str | None = None,
        at: float | None = None,
    ) -> str:
        """Schedule an initial reservation plus automatic PR_NACK retries."""
        sequence_time = self.now if at is None else float(at)
        if sequence_time < self.now:
            raise ValueError("Retry sequence cannot be scheduled in the past.")
        self._validate_retry_packet(packet)

        resolved_flow_id = flow_id or f"flow-{packet.source}-{packet.destination}"
        key = (resolved_flow_id, int(packet.packet_id), int(packet.current_hop_index))
        if key in self._retry_key_to_id:
            raise RuntimeError("A retry sequence already exists for this packet segment.")

        self._retry_sequence += 1
        retry_id = (
            f"{resolved_flow_id}:packet-{packet.packet_id}:"
            f"segment-{packet.current_hop_index}:retry-sequence-{self._retry_sequence}"
        )
        retry_record = ReservationRetryRecord(
            retry_id=retry_id,
            flow_id=resolved_flow_id,
            packet_id=int(packet.packet_id),
            path=tuple(int(node_id) for node_id in packet.route),
            segment_start_index=int(packet.current_hop_index),
            scheduled_at=sequence_time,
            retry_limit=self.config.retry_limit,
        )
        self.retry_records[retry_id] = retry_record
        self._retry_packets[retry_id] = packet
        self._retry_key_to_id[key] = retry_id
        self.simulator.schedule_at(
            sequence_time,
            lambda: self._begin_retry_sequence(retry_record, packet),
            event_type="RETRY_SEQUENCE_START",
            priority=self.PRIORITY_RETRY_SEQUENCE_START,
        )
        return retry_id

    def _validate_retry_packet(self, packet: Packet) -> None:
        route = tuple(int(node_id) for node_id in packet.route)
        if len(route) < 2:
            raise ValueError("Fixed-PRMAC retry requires a route with at least one hop.")
        start_index = int(packet.current_hop_index)
        if not 0 <= start_index < len(route) - 1:
            raise ValueError("Packet must have at least one remaining hop to reserve.")
        if int(packet.current_node) != route[start_index]:
            raise RuntimeError("Packet current node is inconsistent with route.")
        if packet.status == PacketStatus.DROPPED:
            raise RuntimeError("A DROPPED packet cannot start another retry sequence.")

    def _begin_retry_sequence(
        self,
        retry_record: ReservationRetryRecord,
        packet: Packet,
    ) -> None:
        if retry_record.status != ReservationRetryStatus.SCHEDULED:
            return
        retry_record.status = ReservationRetryStatus.ATTEMPTING
        retry_record.started_at = self.now
        self.metrics.retry_sequences_started += 1
        self._schedule_attempt(
            retry_record,
            packet,
            attempt_number=1,
            contention_window=self.config.fixed_cw_min,
            backoff_slots=None,
            backoff_delay=0.0,
        )

    def _schedule_attempt(
        self,
        retry_record: ReservationRetryRecord,
        packet: Packet,
        *,
        attempt_number: int,
        contention_window: int,
        backoff_slots: int | None,
        backoff_delay: float,
    ) -> str:
        reservation_id = super().schedule_reservation(
            packet,
            flow_id=retry_record.flow_id,
            at=self.now,
        )
        attempt = ReservationRetryAttempt(
            attempt_number=attempt_number,
            reservation_id=reservation_id,
            contention_window=contention_window,
            scheduled_at=self.now,
            backoff_slots_before_attempt=backoff_slots,
            backoff_delay_before_attempt=backoff_delay,
        )
        retry_record.attempts.append(attempt)
        self._reservation_to_retry_id[reservation_id] = retry_record.retry_id
        self._attempt_by_reservation_id[reservation_id] = attempt
        self.metrics.retry_attempts_scheduled += 1

        reservation = self.table.get(reservation_id)
        if attempt_number == 1:
            self._trace(
                "RETRY_SEQUENCE_START",
                reservation,
                node_id=reservation.initiator,
                detail=(
                    f"retry_id={retry_record.retry_id}, "
                    f"retry_limit={retry_record.retry_limit}"
                ),
            )
        self._trace(
            "RETRY_ATTEMPT_SCHEDULED",
            reservation,
            node_id=reservation.initiator,
            detail=(
                f"retry_id={retry_record.retry_id}, "
                f"attempt={attempt_number}, cw={contention_window}, "
                f"backoff_slots={backoff_slots if backoff_slots is not None else 0}, "
                f"backoff_delay={backoff_delay:.9f}s"
            ),
        )
        return reservation_id

    def _begin_reservation(self, record: ReservationRecord) -> None:
        """Begin one attempt while exposing the actual CW used by Day12."""
        if record.status != ReservationStatus.PENDING:
            return

        attempt = self._attempt_by_reservation_id.get(record.reservation_id)
        actual_cw = (
            attempt.contention_window
            if attempt is not None
            else self.config.fixed_cw_min
        )
        if attempt is not None:
            self._trace(
                "RETRY_ATTEMPT_START",
                record,
                node_id=record.initiator,
                detail=(
                    f"attempt={attempt.attempt_number}, "
                    f"cw={actual_cw}, "
                    f"backoff_slots="
                    f"{attempt.backoff_slots_before_attempt if attempt.backoff_slots_before_attempt is not None else 0}"
                ),
            )

        # Replicate the inherited Day09 start operation locally so the trace
        # reports Day12's expanded retry CW instead of always printing CWmin.
        self.metrics.reservation_requests += 1
        self._trace(
            "RESERVATION_START",
            record,
            node_id=record.initiator,
            detail=(
                f"requested_k={record.requested_hops}, "
                f"effective_k={record.effective_hops}, "
                f"cw_init={actual_cw}"
            ),
        )
        self.simulator.schedule(
            0.0,
            lambda: self._transmit_pr_req(record, 0),
            event_type="PR_REQ_TX",
            priority=self.PRIORITY_CONTROL_TX,
        )

    def _receive_pr_ack(
        self,
        record: ReservationRecord,
        reverse_index: int,
        frame: PRMACFrame,
    ) -> None:
        super()._receive_pr_ack(record, reverse_index, frame)
        if record.status != ReservationStatus.ACTIVE:
            return

        retry_id = self._reservation_to_retry_id.get(record.reservation_id)
        if retry_id is None:
            return
        retry_record = self.retry_records[retry_id]
        if retry_record.status in {
            ReservationRetryStatus.SUCCEEDED,
            ReservationRetryStatus.FAILED,
        }:
            return

        attempt = self._attempt_by_reservation_id[record.reservation_id]
        attempt.status = ReservationStatus.ACTIVE
        attempt.completed_at = self.now
        retry_record.status = ReservationRetryStatus.SUCCEEDED
        retry_record.succeeded_at = self.now
        retry_record.successful_reservation_id = record.reservation_id
        if attempt.attempt_number == 1:
            self.metrics.first_attempt_successes += 1
        else:
            self.metrics.retry_successes += 1

        delay = retry_record.completion_delay
        if delay is None:
            raise RuntimeError("Successful retry sequence must expose a delay.")
        self.metrics.retry_completion_delays.append(delay)
        self._trace(
            "RETRY_SEQUENCE_SUCCEEDED",
            record,
            node_id=record.initiator,
            detail=(
                f"retry_id={retry_id}, attempts={retry_record.total_attempts}, "
                f"retries_used={retry_record.retries_used}, "
                f"completion_delay={delay:.9f}s"
            ),
        )

    def _receive_pr_nack(
        self,
        record: ReservationRecord,
        reverse_index: int,
        frame: PRMACFrame,
        reason: str,
    ) -> None:
        super()._receive_pr_nack(record, reverse_index, frame, reason)
        if record.status != ReservationStatus.REJECTED:
            return

        retry_id = self._reservation_to_retry_id.get(record.reservation_id)
        if retry_id is None:
            return
        retry_record = self.retry_records[retry_id]
        attempt = self._attempt_by_reservation_id[record.reservation_id]
        if attempt.status != ReservationStatus.PENDING:
            return

        attempt.status = ReservationStatus.REJECTED
        attempt.completed_at = self.now
        attempt.failure_reason = reason
        self._handle_rejected_attempt(retry_record, packet=self._retry_packets[retry_id], record=record)

    def _handle_rejected_attempt(
        self,
        retry_record: ReservationRetryRecord,
        *,
        packet: Packet,
        record: ReservationRecord,
    ) -> None:
        attempt = self._attempt_by_reservation_id[record.reservation_id]
        retries_already_used = attempt.attempt_number - 1
        if retries_already_used >= self.config.retry_limit:
            final_reason = (
                f"retry_limit_exhausted={self.config.retry_limit}; "
                f"attempts={retry_record.total_attempts}; "
                f"last_reason={record.failure_reason}"
            )
            failed_record = self.table.fail_exhausted(
                record.reservation_id,
                at=self.now,
                reason=final_reason,
            )
            attempt.status = ReservationStatus.FAILED
            attempt.failure_reason = final_reason
            retry_record.status = ReservationRetryStatus.FAILED
            retry_record.failed_at = self.now
            retry_record.failure_reason = final_reason
            packet.status = PacketStatus.DROPPED
            self.metrics.retry_exhausted_failures += 1
            delay = retry_record.completion_delay
            if delay is None:
                raise RuntimeError("Failed retry sequence must expose a delay.")
            self.metrics.retry_completion_delays.append(delay)
            self._trace(
                "RETRY_SEQUENCE_FAILED",
                failed_record,
                node_id=failed_record.initiator,
                detail=(
                    f"retry_id={retry_record.retry_id}, "
                    f"attempts={retry_record.total_attempts}, "
                    f"retries_used={retry_record.retries_used}, "
                    f"completion_delay={delay:.9f}s; {final_reason}"
                ),
            )
            return

        retry_number = attempt.attempt_number
        next_cw = self.config.contention_window_for_retry(retry_number)
        backoff_slots = self._rng.randint(0, next_cw)
        backoff_delay = self.config.retry_backoff_delay(backoff_slots)
        retry_record.status = ReservationRetryStatus.BACKING_OFF
        packet.increment_retry()
        self.metrics.reservation_retries_scheduled += 1
        self.metrics.total_retry_backoff_slots += backoff_slots
        self.metrics.retry_backoff_delays.append(backoff_delay)
        self._trace(
            "RETRY_BACKOFF_START",
            record,
            node_id=record.initiator,
            detail=(
                f"retry_id={retry_record.retry_id}, "
                f"next_attempt={attempt.attempt_number + 1}, "
                f"retry_number={retry_number}, cw={next_cw}, "
                f"backoff_slots={backoff_slots}, "
                f"backoff_delay={backoff_delay:.9f}s"
            ),
        )
        self.simulator.schedule(
            backoff_delay,
            lambda: self._start_retry_attempt(
                retry_record,
                packet,
                attempt_number=attempt.attempt_number + 1,
                contention_window=next_cw,
                backoff_slots=backoff_slots,
                backoff_delay=backoff_delay,
            ),
            event_type="RESERVATION_RETRY_START",
            priority=self.PRIORITY_RETRY_ATTEMPT_START,
        )

    def _start_retry_attempt(
        self,
        retry_record: ReservationRetryRecord,
        packet: Packet,
        *,
        attempt_number: int,
        contention_window: int,
        backoff_slots: int,
        backoff_delay: float,
    ) -> None:
        if retry_record.status != ReservationRetryStatus.BACKING_OFF:
            return
        retry_record.status = ReservationRetryStatus.ATTEMPTING
        self._schedule_attempt(
            retry_record,
            packet,
            attempt_number=attempt_number,
            contention_window=contention_window,
            backoff_slots=backoff_slots,
            backoff_delay=backoff_delay,
        )

    def retry_snapshot(self) -> list[dict[str, object]]:
        snapshot: list[dict[str, object]] = []
        for retry_record in self.retry_records.values():
            item = {
                **asdict(retry_record),
                "status": retry_record.status.value,
                "completion_delay": retry_record.completion_delay,
                "attempts": [],
            }
            attempts: list[dict[str, object]] = []
            for attempt in retry_record.attempts:
                attempt_item = asdict(attempt)
                attempt_item["status"] = attempt.status.value
                attempts.append(attempt_item)
            item["attempts"] = attempts
            snapshot.append(item)
        return snapshot

    def export_retry_summary_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": asdict(self.config),
            "metrics": self.metrics.summary(self.table),
            "retry_sequences": self.retry_snapshot(),
            "forwardings": self.forwarding_snapshot(),
            "reservations": self.conflict_snapshot(),
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination


__all__ = [
    "Day12FixedPRMACConfig",
    "Day12FixedPRMACMetrics",
    "Day12ReservationTable",
    "FixedPRMACRetryController",
    "ReservationRetryAttempt",
    "ReservationRetryRecord",
    "ReservationRetryStatus",
]
