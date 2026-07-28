"""Day15: joint (K, CW) action space and distributed local policy.

The implementation inherits the frozen RL-PRMAC design:
- one decision at a reservation-segment start node before initial DIFS/backoff;
- K in {1, 2, 3};
- initial CW in {15, 31};
- Fixed-PRMAC baseline action (K=2, CW=15) remains available;
- K must not exceed the packet's locally known remaining hops;
- one selected action remains fixed for the complete segment retry sequence;
- PR_NACK retries apply BEB starting from the action-selected initial CW;
- each node owns its local sparse Q-value table and executes epsilon-greedy locally.

This module deliberately does NOT implement rewards, Bellman/Q-learning updates,
training loops, a centralized controller, or Day13 protocol integration. Those
belong to later project days.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import random
from typing import Any, Iterable

from rl_prmac_state import RLState, enumerate_state_space_size


ACTION_DESIGN_VERSION = "Day15-Final-action-policy-v1"
DEFAULT_K_VALUES: tuple[int, ...] = (1, 2, 3)
DEFAULT_CW_VALUES: tuple[int, ...] = (15, 31)
DEFAULT_CW_MAX = 1023
DEFAULT_SLOT_TIME = 20e-6
DEFAULT_DIFS_TIME = 50e-6


def _is_power_of_two_minus_one(value: int) -> bool:
    return value > 0 and ((value + 1) & value) == 0


def _require_unique_ascending_positive(values: tuple[int, ...], *, name: str) -> None:
    if not values:
        raise ValueError(f"{name} cannot be empty.")
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{name} must be unique and ascending.")
    if any(value <= 0 for value in values):
        raise ValueError(f"Every value in {name} must be positive.")



@dataclass(frozen=True, order=True, slots=True)
class JointAction:
    """One segment-level RL-PRMAC action."""

    reservation_length_k: int
    initial_cw: int

    def __post_init__(self) -> None:
        if self.reservation_length_k <= 0:
            raise ValueError("reservation_length_k must be positive.")
        if self.initial_cw <= 0:
            raise ValueError("initial_cw must be positive.")
        if not _is_power_of_two_minus_one(self.initial_cw):
            raise ValueError("initial_cw must have the form 2^m - 1.")

    def as_tuple(self) -> tuple[int, int]:
        return (self.reservation_length_k, self.initial_cw)


FIXED_BASELINE_ACTION = JointAction(2, 15)


@dataclass(frozen=True, slots=True)
class JointActionSpace:
    """Frozen six-action space inherited from the project design."""

    k_values: tuple[int, ...] = DEFAULT_K_VALUES
    cw_values: tuple[int, ...] = DEFAULT_CW_VALUES
    cw_max: int = DEFAULT_CW_MAX
    slot_time: float = DEFAULT_SLOT_TIME
    difs_time: float = DEFAULT_DIFS_TIME

    def __post_init__(self) -> None:
        _require_unique_ascending_positive(self.k_values, name="k_values")
        _require_unique_ascending_positive(self.cw_values, name="cw_values")
        if not all(_is_power_of_two_minus_one(cw) for cw in self.cw_values):
            raise ValueError("Every CW must have the form 2^m - 1.")
        if self.cw_max < max(self.cw_values):
            raise ValueError("cw_max must cover every initial CW action.")
        if not _is_power_of_two_minus_one(self.cw_max):
            raise ValueError("cw_max must have the form 2^m - 1.")
        if self.slot_time < 0 or self.difs_time < 0:
            raise ValueError("slot_time and difs_time cannot be negative.")
        if FIXED_BASELINE_ACTION not in self.actions:
            raise ValueError("The action space must preserve baseline (K=2, CW=15).")

    @property
    def actions(self) -> tuple[JointAction, ...]:
        """Stable K-major, CW-minor action order a0...a5."""
        return tuple(
            JointAction(k, cw)
            for k in self.k_values
            for cw in self.cw_values
        )

    @property
    def fixed_baseline_action(self) -> JointAction:
        return FIXED_BASELINE_ACTION

    @property
    def dense_state_action_upper_bound(self) -> int:
        return enumerate_state_space_size() * len(self.actions)

    def action_to_index(self, action: JointAction) -> int:
        try:
            return self.actions.index(action)
        except ValueError as exc:
            raise ValueError(f"Action is outside the frozen space: {action}") from exc

    def index_to_action(self, action_index: int) -> JointAction:
        if not 0 <= action_index < len(self.actions):
            raise IndexError("action_index is outside the frozen action space.")
        return self.actions[action_index]

    def valid_action_indices(self, remaining_hops: int) -> tuple[int, ...]:
        self._validate_remaining_hops(remaining_hops)
        return tuple(
            index
            for index, action in enumerate(self.actions)
            if action.reservation_length_k <= remaining_hops
        )

    def valid_actions(self, remaining_hops: int) -> tuple[JointAction, ...]:
        return tuple(
            self.actions[index]
            for index in self.valid_action_indices(remaining_hops)
        )

    def legal_mask(self, remaining_hops: int) -> tuple[bool, ...]:
        legal = set(self.valid_action_indices(remaining_hops))
        return tuple(index in legal for index in range(len(self.actions)))

    def validate_action(self, action: JointAction, *, remaining_hops: int) -> None:
        self._validate_remaining_hops(remaining_hops)
        self.action_to_index(action)
        if action.reservation_length_k > remaining_hops:
            raise ValueError(
                "Illegal action: reservation_length_k exceeds remaining_hops. "
                "RL actions are masked, not silently truncated."
            )

    def contention_window_for_retry(
        self,
        action: JointAction,
        retry_number: int,
    ) -> int:
        """Return CW for retry_number=0,1,... using action-rooted BEB."""
        self.action_to_index(action)
        if retry_number < 0:
            raise ValueError("retry_number cannot be negative.")
        expanded = (action.initial_cw + 1) * (2**retry_number) - 1
        return min(expanded, self.cw_max)

    def sample_backoff_slots(
        self,
        action: JointAction,
        *,
        retry_number: int,
        rng: random.Random,
    ) -> int:
        cw = self.contention_window_for_retry(action, retry_number)
        return rng.randint(0, cw)

    def access_delay(self, backoff_slots: int) -> float:
        if backoff_slots < 0:
            raise ValueError("backoff_slots cannot be negative.")
        return self.difs_time + backoff_slots * self.slot_time

    @staticmethod
    def _validate_remaining_hops(remaining_hops: int) -> None:
        if remaining_hops <= 0:
            raise ValueError("remaining_hops must be positive at a decision epoch.")


@dataclass(slots=True)
class SparseLocalQTable:
    """Node-owned Q-value storage without a Day16 update rule."""

    node_id: int
    action_count: int
    _values: dict[tuple[RLState, int], float] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.node_id < 0:
            raise ValueError("node_id cannot be negative.")
        if self.action_count <= 0:
            raise ValueError("action_count must be positive.")

    def get(self, state: RLState, action_index: int) -> float:
        self._validate_index(action_index)
        return float(self._values.get((state, action_index), 0.0))

    def set_value(self, state: RLState, action_index: int, value: float) -> None:
        """Assign a value for initialization or policy tests.

        This is storage only. Day16 defines the temporal-difference update rule.
        """
        self._validate_index(action_index)
        if not math.isfinite(value):
            raise ValueError("Q value must be finite.")
        self._values[(state, action_index)] = float(value)

    def values_for(self, state: RLState) -> tuple[float, ...]:
        return tuple(self.get(state, index) for index in range(self.action_count))

    @property
    def entry_count(self) -> int:
        return len(self._values)

    def _validate_index(self, action_index: int) -> None:
        if not 0 <= action_index < self.action_count:
            raise IndexError("action_index is outside this local Q table.")


class SelectionMode(str, Enum):
    EXPLORE = "explore"
    EXPLOIT = "exploit"


@dataclass(frozen=True, slots=True)
class SegmentActionDecision:
    """Auditable action selected once for one complete segment retry sequence."""

    decision_id: str
    node_id: int
    state: RLState
    remaining_hops: int
    action: JointAction
    action_index: int
    selected_at: float
    selection_mode: SelectionMode
    epsilon: float
    legal_action_indices: tuple[int, ...]
    action_scope: str = "one_segment_retry_sequence"

    def contention_window_for_retry(
        self,
        action_space: JointActionSpace,
        retry_number: int,
    ) -> int:
        action_space.validate_action(self.action, remaining_hops=self.remaining_hops)
        return action_space.contention_window_for_retry(self.action, retry_number)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "node_id": self.node_id,
            "state": list(self.state.as_tuple()),
            "remaining_hops": self.remaining_hops,
            "action": list(self.action.as_tuple()),
            "action_index": self.action_index,
            "selected_at": self.selected_at,
            "selection_mode": self.selection_mode.value,
            "epsilon": self.epsilon,
            "legal_action_indices": list(self.legal_action_indices),
            "action_scope": self.action_scope,
        }


class LocalEpsilonGreedyPolicy:
    """Distributed epsilon-greedy policy executed by one segment start node."""

    def __init__(
        self,
        *,
        node_id: int,
        action_space: JointActionSpace | None = None,
        q_table: SparseLocalQTable | None = None,
        epsilon: float = 0.10,
        random_seed: int = 7,
    ) -> None:
        if node_id < 0:
            raise ValueError("node_id cannot be negative.")
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be within [0, 1].")
        self.node_id = node_id
        self.action_space = action_space or JointActionSpace()
        self.q_table = q_table or SparseLocalQTable(
            node_id=node_id,
            action_count=len(self.action_space.actions),
        )
        if self.q_table.node_id != node_id:
            raise ValueError("A node cannot use another node's local Q table.")
        if self.q_table.action_count != len(self.action_space.actions):
            raise ValueError("Q table action_count must match the action space.")
        self.epsilon = float(epsilon)
        self._rng = random.Random(random_seed)
        self._decision_sequence = 0

    def select_action(
        self,
        *,
        state: RLState,
        remaining_hops: int,
        selected_at: float = 0.0,
    ) -> SegmentActionDecision:
        if selected_at < 0:
            raise ValueError("selected_at cannot be negative.")
        legal_indices = self.action_space.valid_action_indices(remaining_hops)
        explore = self._rng.random() < self.epsilon
        if explore:
            selected_index = self._rng.choice(legal_indices)
            mode = SelectionMode.EXPLORE
        else:
            selected_index = self._greedy_index(state, legal_indices)
            mode = SelectionMode.EXPLOIT

        action = self.action_space.index_to_action(selected_index)
        self.action_space.validate_action(action, remaining_hops=remaining_hops)
        self._decision_sequence += 1
        return SegmentActionDecision(
            decision_id=f"node-{self.node_id}:decision-{self._decision_sequence}",
            node_id=self.node_id,
            state=state,
            remaining_hops=remaining_hops,
            action=action,
            action_index=selected_index,
            selected_at=float(selected_at),
            selection_mode=mode,
            epsilon=self.epsilon,
            legal_action_indices=legal_indices,
        )

    def _greedy_index(
        self,
        state: RLState,
        legal_indices: Iterable[int],
    ) -> int:
        candidates = tuple(legal_indices)
        if not candidates:
            raise RuntimeError("At least one legal action is required.")
        values = tuple(self.q_table.get(state, index) for index in candidates)
        maximum = max(values)
        ties = tuple(
            index for index, value in zip(candidates, values) if value == maximum
        )
        # Seeded random tie-breaking avoids permanent low-index bias while keeping
        # experiments reproducible.
        return self._rng.choice(ties)
