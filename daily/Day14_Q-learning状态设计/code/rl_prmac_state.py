"""Day14: local state design for distributed tabular Q-learning in RL-PRMAC.

Scope is strictly limited to:
- locally observable raw observations at each reservation-segment start node;
- deterministic discretization into a bounded tabular state;
- state-space validation.

This module deliberately does NOT implement:
- (K, CW) action selection;
- epsilon-greedy policy;
- reward calculation;
- Q-value update or training;
- centralized/global-state control.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ReservationOutcome(IntEnum):
    """Most recent locally observed reservation-segment result."""

    NONE = 0
    SUCCESS = 1
    FAILURE = 2


class ChannelBusyBin(IntEnum):
    """Locally measured CCA busy-ratio class."""

    UNKNOWN = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True, slots=True)
class LocalObservation:
    """Raw information available at one reservation-segment start node."""

    node_id: int
    packet_id: int
    flow_id: str
    observed_at: float
    remaining_hops: int
    local_queue_length: int
    queue_limit: int
    priority: int
    last_reservation_succeeded: bool | None
    recent_mean_retries: float
    channel_busy_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.node_id < 0:
            raise ValueError("node_id cannot be negative.")
        if self.packet_id < 0:
            raise ValueError("packet_id cannot be negative.")
        if not self.flow_id:
            raise ValueError("flow_id cannot be empty.")
        if self.observed_at < 0:
            raise ValueError("observed_at cannot be negative.")
        if self.remaining_hops <= 0:
            raise ValueError("remaining_hops must be positive at a decision epoch.")
        if self.queue_limit <= 0:
            raise ValueError("queue_limit must be positive.")
        if not 1 <= self.local_queue_length <= self.queue_limit:
            raise ValueError(
                "local_queue_length must include the active FIFO head and "
                "stay within queue_limit."
            )
        if self.recent_mean_retries < 0:
            raise ValueError("recent_mean_retries cannot be negative.")
        if self.channel_busy_ratio is not None and not 0.0 <= self.channel_busy_ratio <= 1.0:
            raise ValueError("channel_busy_ratio must be within [0, 1].")


@dataclass(frozen=True, slots=True)
class RLState:
    """Hashable discrete state used as a future tabular Q key."""

    remaining_hops_bin: int
    queue_length_bin: int
    last_reservation_outcome: int
    retry_intensity_bin: int
    priority_bin: int
    channel_busy_bin: int

    def as_tuple(self) -> tuple[int, int, int, int, int, int]:
        return (
            self.remaining_hops_bin,
            self.queue_length_bin,
            self.last_reservation_outcome,
            self.retry_intensity_bin,
            self.priority_bin,
            self.channel_busy_bin,
        )


@dataclass(frozen=True, slots=True)
class StateEncoder:
    """Deterministic local-state discretizer."""

    busy_low_upper: float = 0.25
    busy_medium_upper: float = 0.60

    def __post_init__(self) -> None:
        if not 0.0 < self.busy_low_upper < self.busy_medium_upper < 1.0:
            raise ValueError("Busy-ratio thresholds must satisfy 0 < low < medium < 1.")

    def encode(self, observation: LocalObservation) -> RLState:
        return RLState(
            remaining_hops_bin=self._remaining_hops_bin(observation.remaining_hops),
            queue_length_bin=self._queue_length_bin(observation.local_queue_length),
            last_reservation_outcome=self._outcome_bin(
                observation.last_reservation_succeeded
            ),
            retry_intensity_bin=self._retry_bin(observation.recent_mean_retries),
            priority_bin=1 if observation.priority > 0 else 0,
            channel_busy_bin=int(self._busy_bin(observation.channel_busy_ratio)),
        )

    @staticmethod
    def _remaining_hops_bin(remaining_hops: int) -> int:
        if remaining_hops == 1:
            return 0
        if remaining_hops == 2:
            return 1
        if remaining_hops <= 4:
            return 2
        return 3

    @staticmethod
    def _queue_length_bin(queue_length: int) -> int:
        if queue_length == 1:
            return 0
        if queue_length <= 3:
            return 1
        if queue_length <= 7:
            return 2
        return 3

    @staticmethod
    def _outcome_bin(last_succeeded: bool | None) -> int:
        if last_succeeded is None:
            return int(ReservationOutcome.NONE)
        return int(
            ReservationOutcome.SUCCESS if last_succeeded else ReservationOutcome.FAILURE
        )

    @staticmethod
    def _retry_bin(mean_retries: float) -> int:
        if mean_retries == 0:
            return 0
        if mean_retries <= 1:
            return 1
        if mean_retries <= 2:
            return 2
        return 3

    def _busy_bin(self, busy_ratio: float | None) -> ChannelBusyBin:
        if busy_ratio is None:
            return ChannelBusyBin.UNKNOWN
        if busy_ratio < self.busy_low_upper:
            return ChannelBusyBin.LOW
        if busy_ratio < self.busy_medium_upper:
            return ChannelBusyBin.MEDIUM
        return ChannelBusyBin.HIGH


def enumerate_state_space_size() -> int:
    """Return the declared maximum number of discrete states."""

    # remaining hops × local queue × previous outcome × retries
    # × priority × channel busy ratio
    return 4 * 4 * 3 * 4 * 2 * 4
