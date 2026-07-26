"""Day10 Fixed-PRMAC reservation conflict model and PR_NACK propagation.

Scope is deliberately limited to:
- conflicts against existing ACTIVE reservations;
- directed-request traversal with local resource checks at each PR_REQ receiver;
- undirected-link exclusivity, node exclusivity, and half-open time windows;
- reverse PR_NACK and terminal REJECTED state.

It does not implement retry/backoff, DATA/H_ACK forwarding, end-to-end
Fixed-PRMAC, or reinforcement learning.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

# Keep Day10 first so Day09's controller imports the Day10-compatible message
# models (same API plus REJECTED/rejected_at), without editing Day09 files.
# Force a deterministic import order. When a Python script is executed directly,
# CURRENT_DIR is already present in sys.path. Merely skipping existing entries
# would allow DAY09_CODE to be inserted ahead of Day10 and would load Day09's
# ReservationStatus (which has no REJECTED state).
_import_paths = [CURRENT_DIR, DAY09_CODE, DAY03_CODE]
for path in _import_paths:
    path_text = str(path)
    while path_text in sys.path:
        sys.path.remove(path_text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from packet import Packet  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402

from fixed_prmac_messages import (  # noqa: E402
    PRMACFrame,
    PRMACFrameType,
    ReservationRecord,
    ReservationStatus,
    ReservedLink,
)
from fixed_prmac_reservation import (  # type: ignore  # noqa: E402
    FixedPRMACConfig,
    FixedPRMACMetrics,
    FixedPRMACReservationController,
    ReservationTable,
)


@dataclass(frozen=True, slots=True)
class Day10FixedPRMACConfig(FixedPRMACConfig):
    """Day09 parameters plus PR_NACK serialization size."""

    pr_nack_size_bytes: int = 24

    def __post_init__(self) -> None:
        FixedPRMACConfig.__post_init__(self)
        if self.pr_nack_size_bytes <= 0:
            raise ValueError("pr_nack_size_bytes must be positive.")

    def frame_tx_time(self, frame_type: PRMACFrameType) -> float:
        if frame_type == PRMACFrameType.PR_NACK:
            return self.pr_nack_size_bytes * 8 / self.control_rate_bps
        return FixedPRMACConfig.frame_tx_time(self, frame_type)


@dataclass(frozen=True, slots=True)
class ReservationConflict:
    """Deterministic description of one detected resource conflict."""

    conflict_type: str
    resource: str
    existing_reservation_id: str
    candidate_window_start: float
    candidate_window_end: float
    existing_window_start: float
    existing_window_end: float

    @property
    def reason(self) -> str:
        return (
            f"{self.conflict_type}: resource={self.resource}; "
            f"existing={self.existing_reservation_id}; "
            f"candidate=[{self.candidate_window_start:.9f},"
            f"{self.candidate_window_end:.9f}); "
            f"existing_window=[{self.existing_window_start:.9f},"
            f"{self.existing_window_end:.9f})"
        )


class ReservationConflictPolicy:
    """Local node/link exclusivity policy for one PR_REQ hop.

    Rules:
    1. Only ACTIVE records occupy resources.
    2. Time windows use half-open intervals [start, end).
    3. A directed link conflicts with the same physical link in either direction.
    4. Otherwise, sharing either endpoint node conflicts.
    """

    @staticmethod
    def _windows_overlap(
        start_a: float,
        end_a: float,
        start_b: float,
        end_b: float,
    ) -> bool:
        return start_a < end_b and start_b < end_a

    @staticmethod
    def _physical_link(link: ReservedLink) -> tuple[int, int]:
        return tuple(sorted((link.sender, link.receiver)))

    def find_conflict(
        self,
        *,
        candidate: ReservationRecord,
        link_index: int,
        active_records: tuple[ReservationRecord, ...],
        now: float,
    ) -> ReservationConflict | None:
        candidate_link = candidate.reserved_links[link_index]
        candidate_nodes = {candidate_link.sender, candidate_link.receiver}
        candidate_start = float(now)
        candidate_end = candidate_start + candidate.duration
        candidate_physical_link = self._physical_link(candidate_link)

        for existing in active_records:
            if existing.reservation_id == candidate.reservation_id:
                continue
            if existing.activated_at is None or existing.expires_at is None:
                continue
            if not self._windows_overlap(
                candidate_start,
                candidate_end,
                existing.activated_at,
                existing.expires_at,
            ):
                continue

            for existing_link in existing.reserved_links:
                if self._physical_link(existing_link) == candidate_physical_link:
                    return ReservationConflict(
                        conflict_type="LINK_CONFLICT",
                        resource=(
                            f"{candidate_physical_link[0]}-"
                            f"{candidate_physical_link[1]}"
                        ),
                        existing_reservation_id=existing.reservation_id,
                        candidate_window_start=candidate_start,
                        candidate_window_end=candidate_end,
                        existing_window_start=existing.activated_at,
                        existing_window_end=existing.expires_at,
                    )

            existing_nodes = {
                node_id
                for existing_link in existing.reserved_links
                for node_id in (existing_link.sender, existing_link.receiver)
            }
            shared_nodes = sorted(candidate_nodes & existing_nodes)
            if shared_nodes:
                return ReservationConflict(
                    conflict_type="NODE_CONFLICT",
                    resource=f"node-{shared_nodes[0]}",
                    existing_reservation_id=existing.reservation_id,
                    candidate_window_start=candidate_start,
                    candidate_window_end=candidate_end,
                    existing_window_start=existing.activated_at,
                    existing_window_end=existing.expires_at,
                )

        return None


class Day10ReservationTable(ReservationTable):
    """Day09 lifecycle table extended with terminal rejection."""

    def reject(
        self,
        reservation_id: str,
        *,
        at: float,
        reason: str,
    ) -> ReservationRecord:
        record = self.get(reservation_id)
        if record.status != ReservationStatus.PENDING:
            raise RuntimeError(
                "Only PENDING reservations may be rejected, "
                f"got {record.status.value}."
            )
        record.status = ReservationStatus.REJECTED
        record.rejected_at = float(at)
        record.failure_reason = reason
        return record


@dataclass(slots=True)
class Day10FixedPRMACMetrics(FixedPRMACMetrics):
    """Day09 metrics plus rejection/conflict counters."""

    rejected_reservations: int = 0
    link_conflicts: int = 0
    node_conflicts: int = 0
    pr_nack_frames_sent: int = 0

    def record_frame(
        self,
        frame_type: PRMACFrameType,
        config: FixedPRMACConfig,
    ) -> None:
        if frame_type == PRMACFrameType.PR_NACK:
            if not isinstance(config, Day10FixedPRMACConfig):
                raise TypeError("PR_NACK requires Day10FixedPRMACConfig.")
            self.control_frames_sent += 1
            self.control_bytes_sent += config.pr_nack_size_bytes
            self.pr_nack_frames_sent += 1
            return
        FixedPRMACMetrics.record_frame(self, frame_type, config)

    def summary(self, table: ReservationTable) -> dict[str, int | float]:
        payload = FixedPRMACMetrics.summary(self, table)
        payload.update(
            {
                "rejected_reservations": self.rejected_reservations,
                "link_conflicts": self.link_conflicts,
                "node_conflicts": self.node_conflicts,
                "pr_nack_frames_sent": self.pr_nack_frames_sent,
            }
        )
        return payload


class FixedPRMACConflictController(FixedPRMACReservationController):
    """Day09 control plane extended only with Day10 conflict rejection."""

    def __init__(
        self,
        *,
        simulator: Simulator,
        config: Day10FixedPRMACConfig | None = None,
        adjacency: dict[int, set[int]] | None = None,
        table: Day10ReservationTable | None = None,
        metrics: Day10FixedPRMACMetrics | None = None,
        conflict_policy: ReservationConflictPolicy | None = None,
    ) -> None:
        resolved_config = config or Day10FixedPRMACConfig()
        resolved_table = table or Day10ReservationTable()
        resolved_metrics = metrics or Day10FixedPRMACMetrics()
        super().__init__(
            simulator=simulator,
            config=resolved_config,
            adjacency=adjacency,
            table=resolved_table,
            metrics=resolved_metrics,
        )
        self.conflict_policy = conflict_policy or ReservationConflictPolicy()

    @property
    def config(self) -> Day10FixedPRMACConfig:
        return self._config

    @config.setter
    def config(self, value: Day10FixedPRMACConfig) -> None:
        self._config = value

    @property
    def table(self) -> Day10ReservationTable:
        return self._table

    @table.setter
    def table(self, value: Day10ReservationTable) -> None:
        self._table = value

    @property
    def metrics(self) -> Day10FixedPRMACMetrics:
        return self._metrics

    @metrics.setter
    def metrics(self, value: Day10FixedPRMACMetrics) -> None:
        self._metrics = value

    def _receive_pr_req(
        self,
        record: ReservationRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        if record.status != ReservationStatus.PENDING:
            return

        link = record.reserved_links[link_index]
        self._trace(
            "PR_REQ_RX",
            record,
            node_id=link.receiver,
            frame_type=frame.frame_type.value,
            detail=f"from={link.sender}, link_index={link_index}",
        )

        # Expired ACTIVE records must not retain resources merely because no
        # explicit cleanup event was called before this PR_REQ arrived.
        self.expire_reservations(now=self.now)
        conflict = self.conflict_policy.find_conflict(
            candidate=record,
            link_index=link_index,
            active_records=self.table.active_records,
            now=self.now,
        )
        if conflict is not None:
            if conflict.conflict_type == "LINK_CONFLICT":
                self.metrics.link_conflicts += 1
            else:
                self.metrics.node_conflicts += 1
            self._trace(
                "RESERVATION_CONFLICT",
                record,
                node_id=link.receiver,
                detail=conflict.reason,
            )
            self.simulator.schedule(
                self.config.sifs_time,
                lambda: self._transmit_pr_nack(
                    record,
                    link_index,
                    conflict.reason,
                ),
                event_type="PR_NACK_TX",
                priority=self.PRIORITY_CONTROL_TX,
            )
            return

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

    def _transmit_pr_nack(
        self,
        record: ReservationRecord,
        reverse_index: int,
        reason: str,
    ) -> None:
        if record.status != ReservationStatus.PENDING:
            return
        link = record.reserved_links[reverse_index]
        frame = PRMACFrame(
            frame_type=PRMACFrameType.PR_NACK,
            flow_id=record.flow_id,
            packet_id=record.packet_id,
            sender=link.receiver,
            receiver=link.sender,
            path=record.path,
            segment_start_index=record.segment_start_index,
            requested_hops=record.requested_hops,
            effective_hops=record.effective_hops,
            priority=record.priority,
            duration=record.duration,
            created_at=self.now,
            reserved_links=record.reserved_links[: reverse_index + 1],
            reason=reason,
        )
        self._record_frame(frame)
        self._trace(
            "PR_NACK_TX",
            record,
            node_id=link.receiver,
            frame_type=frame.frame_type.value,
            detail=(
                f"{link.receiver}->{link.sender}, "
                f"reverse_index={reverse_index}; {reason}"
            ),
        )
        self.simulator.schedule(
            self.config.link_delay(PRMACFrameType.PR_NACK),
            lambda: self._receive_pr_nack(
                record,
                reverse_index,
                frame,
                reason,
            ),
            event_type="PR_NACK_RX",
            priority=self.PRIORITY_CONTROL_RX,
        )

    def _receive_pr_nack(
        self,
        record: ReservationRecord,
        reverse_index: int,
        frame: PRMACFrame,
        reason: str,
    ) -> None:
        if record.status != ReservationStatus.PENDING:
            return
        link = record.reserved_links[reverse_index]
        self._trace(
            "PR_NACK_RX",
            record,
            node_id=link.sender,
            frame_type=frame.frame_type.value,
            detail=f"from={link.receiver}, reverse_index={reverse_index}",
        )
        if reverse_index > 0:
            self.simulator.schedule(
                self.config.sifs_time,
                lambda: self._transmit_pr_nack(
                    record,
                    reverse_index - 1,
                    reason,
                ),
                event_type="PR_NACK_TX",
                priority=self.PRIORITY_CONTROL_TX,
            )
            return

        rejected = self.table.reject(
            record.reservation_id,
            at=self.now,
            reason=reason,
        )
        self.metrics.rejected_reservations += 1
        self._trace(
            "RESERVATION_REJECTED",
            rejected,
            node_id=rejected.initiator,
            detail=reason,
        )

    def conflict_snapshot(self) -> list[dict[str, object]]:
        """Return serializable reservation state for debugging/results."""
        return [
            {
                **asdict(record),
                "status": record.status.value,
                "reserved_links": [asdict(link) for link in record.reserved_links],
            }
            for record in self.table.records
        ]


__all__ = [
    "Day10FixedPRMACConfig",
    "Day10FixedPRMACMetrics",
    "Day10ReservationTable",
    "FixedPRMACConflictController",
    "ReservationConflict",
    "ReservationConflictPolicy",
]
