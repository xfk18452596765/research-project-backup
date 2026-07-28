"""Day16: local segment reward, transition assembly, and tabular Q update.

Frozen inheritance from Day14/Day15:
- state remains the Day14 ``RLState``;
- action remains one Day15 ``JointAction(K, CW)`` selected once before the
  initial DIFS/backoff and held for the complete reservation retry sequence;
- each segment-start node owns an independent sparse Q table;
- no centralized controller, global network state, future end-to-end delay,
  per-hop re-decision, or re-decision after PR_NACK is introduced.

Transition semantics
--------------------
One reward belongs to one complete reservation segment.  It is settled after
that segment succeeds and RELEASE completes, or after its retry sequence is
exhausted.  For a non-terminal update, s' is the *next decision state observed
by the same local node*.  This preserves the independent per-node Q tables and
avoids bootstrapping from another node's private table/state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any

from rl_prmac_state import RLState
from rl_prmac_action_policy import (
    JointActionSpace,
    SegmentActionDecision,
    SparseLocalQTable,
)

REWARD_DESIGN_VERSION = "Day16-Final-local-segment-reward-v1"
UPDATE_DESIGN_VERSION = "Day16-Final-local-q-update-v1"
TRANSITION_SCOPE = "one_complete_reservation_segment"
NEXT_STATE_SCOPE = "same_node_next_local_decision_epoch"


class SegmentSettlement(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


def _require_finite(value: float, *, name: str) -> float:
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ValueError(f"{name} must be finite.")
    return resolved


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)


@dataclass(frozen=True, slots=True)
class RewardConfig:
    """Frozen, interpretable default scales and weights for Day16.

    The delay references are local normalization scales, not global statistics.
    They may be tuned in later experiments without changing the reward structure.
    """

    success_bonus: float = 1.00
    failure_penalty: float = 1.25
    progress_weight: float = 0.30
    delivery_bonus: float = 0.35
    service_delay_weight: float = 0.35
    queue_delay_weight: float = 0.10
    retry_pressure_weight: float = 0.25
    control_overhead_weight: float = 0.10
    high_priority_delay_extra: float = 0.50
    service_delay_reference: float = 0.025
    queue_delay_reference: float = 0.050
    reward_min: float = -2.0
    reward_max: float = 2.0

    def __post_init__(self) -> None:
        nonnegative = (
            "success_bonus",
            "failure_penalty",
            "progress_weight",
            "delivery_bonus",
            "service_delay_weight",
            "queue_delay_weight",
            "retry_pressure_weight",
            "control_overhead_weight",
            "high_priority_delay_extra",
        )
        for name in nonnegative:
            value = _require_finite(getattr(self, name), name=name)
            if value < 0:
                raise ValueError(f"{name} cannot be negative.")
        for name in ("service_delay_reference", "queue_delay_reference"):
            value = _require_finite(getattr(self, name), name=name)
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
        lower = _require_finite(self.reward_min, name="reward_min")
        upper = _require_finite(self.reward_max, name="reward_max")
        if lower >= upper:
            raise ValueError("reward_min must be smaller than reward_max.")


@dataclass(frozen=True, slots=True)
class SegmentRewardInput:
    """Locally auditable measurements for one settled reservation segment."""

    decision: SegmentActionDecision
    packet_id: int
    flow_id: str
    priority: int
    queue_delay: float
    settled_at: float
    settlement: SegmentSettlement
    effective_hops: int
    retries_used: int
    retry_limit: int
    pr_nack_count: int
    control_bytes: int
    payload_bytes: int
    packet_delivered: bool = False
    failure_reason: str = ""

    def __post_init__(self) -> None:
        if self.decision.action_scope != "one_segment_retry_sequence":
            raise ValueError("Day16 requires the frozen Day15 segment action scope.")
        if self.packet_id < 0:
            raise ValueError("packet_id cannot be negative.")
        if not self.flow_id:
            raise ValueError("flow_id cannot be empty.")
        if self.priority < 0:
            raise ValueError("priority cannot be negative.")
        queue_delay = _require_finite(self.queue_delay, name="queue_delay")
        settled_at = _require_finite(self.settled_at, name="settled_at")
        if queue_delay < 0:
            raise ValueError("queue_delay cannot be negative.")
        if settled_at < self.decision.selected_at:
            raise ValueError("settled_at cannot precede action selection.")
        if self.retry_limit < 0:
            raise ValueError("retry_limit cannot be negative.")
        if not 0 <= self.retries_used <= self.retry_limit:
            raise ValueError("retries_used must remain within [0, retry_limit].")
        if self.pr_nack_count < 0:
            raise ValueError("pr_nack_count cannot be negative.")
        if self.pr_nack_count > self.retries_used + 1:
            raise ValueError("pr_nack_count cannot exceed failed attempts in the sequence.")
        if self.control_bytes < 0:
            raise ValueError("control_bytes cannot be negative.")
        if self.payload_bytes <= 0:
            raise ValueError("payload_bytes must be positive.")

        selected_k = self.decision.action.reservation_length_k
        if self.settlement == SegmentSettlement.SUCCESS:
            if not 1 <= self.effective_hops <= selected_k:
                raise ValueError("A successful segment must advance 1..selected K hops.")
        else:
            if self.effective_hops != 0:
                raise ValueError("A failed segment cannot report forwarded hops.")
            if self.packet_delivered:
                raise ValueError("A failed segment cannot deliver the packet.")
            if not self.failure_reason:
                raise ValueError("A failed segment must expose a failure_reason.")

        if self.packet_delivered:
            if self.settlement != SegmentSettlement.SUCCESS:
                raise ValueError("packet_delivered requires segment success.")
            if self.effective_hops != self.decision.remaining_hops:
                raise ValueError(
                    "A locally observed final delivery must consume all remaining hops."
                )

    @property
    def service_delay(self) -> float:
        """Post-decision segment time: initial access through success/terminal failure."""

        return float(self.settled_at - self.decision.selected_at)


@dataclass(frozen=True, slots=True)
class RewardBreakdown:
    reward: float
    unclipped_reward: float
    outcome_term: float
    progress_term: float
    delivery_term: float
    service_delay_term: float
    queue_delay_term: float
    retry_pressure_term: float
    control_overhead_term: float
    progress_normalized: float
    service_delay_normalized: float
    queue_delay_normalized: float
    retry_pressure_normalized: float
    control_overhead_normalized: float
    priority_delay_multiplier: float

    def as_dict(self) -> dict[str, float]:
        return {
            field: float(getattr(self, field))
            for field in self.__dataclass_fields__
        }


class LocalSegmentReward:
    """Compute one clipped multi-objective reward from local segment records."""

    def __init__(
        self,
        *,
        config: RewardConfig | None = None,
        action_space: JointActionSpace | None = None,
    ) -> None:
        self.config = config or RewardConfig()
        self.action_space = action_space or JointActionSpace()

    def calculate(self, item: SegmentRewardInput) -> RewardBreakdown:
        decision = item.decision
        self.action_space.validate_action(
            decision.action,
            remaining_hops=decision.remaining_hops,
        )
        expected_index = self.action_space.action_to_index(decision.action)
        if decision.action_index != expected_index:
            raise ValueError("decision action_index does not match the frozen action catalog.")
        if decision.action_index not in decision.legal_action_indices:
            raise ValueError("The settled action was not legal at its decision epoch.")

        max_k = max(self.action_space.k_values)
        progress_norm = _clip(item.effective_hops / max_k, 0.0, 1.0)
        service_norm = _clip(
            item.service_delay / self.config.service_delay_reference,
            0.0,
            1.0,
        )
        queue_norm = _clip(
            item.queue_delay / self.config.queue_delay_reference,
            0.0,
            1.0,
        )
        retry_norm = (
            item.retries_used / item.retry_limit if item.retry_limit > 0 else 0.0
        )
        nack_denominator = item.retry_limit + 1
        nack_norm = item.pr_nack_count / nack_denominator
        retry_pressure_norm = _clip(max(retry_norm, nack_norm), 0.0, 1.0)
        control_norm = _clip(
            item.control_bytes / (item.control_bytes + item.payload_bytes),
            0.0,
            1.0,
        )
        priority_multiplier = 1.0 + (
            self.config.high_priority_delay_extra if item.priority > 0 else 0.0
        )

        succeeded = item.settlement == SegmentSettlement.SUCCESS
        outcome_term = (
            self.config.success_bonus if succeeded else -self.config.failure_penalty
        )
        progress_term = self.config.progress_weight * progress_norm
        delivery_term = self.config.delivery_bonus if item.packet_delivered else 0.0
        service_term = -(
            priority_multiplier
            * self.config.service_delay_weight
            * service_norm
        )
        queue_term = -(
            priority_multiplier
            * self.config.queue_delay_weight
            * queue_norm
        )
        retry_term = -self.config.retry_pressure_weight * retry_pressure_norm
        control_term = -self.config.control_overhead_weight * control_norm
        unclipped = (
            outcome_term
            + progress_term
            + delivery_term
            + service_term
            + queue_term
            + retry_term
            + control_term
        )
        reward = _clip(unclipped, self.config.reward_min, self.config.reward_max)
        return RewardBreakdown(
            reward=reward,
            unclipped_reward=unclipped,
            outcome_term=outcome_term,
            progress_term=progress_term,
            delivery_term=delivery_term,
            service_delay_term=service_term,
            queue_delay_term=queue_term,
            retry_pressure_term=retry_term,
            control_overhead_term=control_term,
            progress_normalized=progress_norm,
            service_delay_normalized=service_norm,
            queue_delay_normalized=queue_norm,
            retry_pressure_normalized=retry_pressure_norm,
            control_overhead_normalized=control_norm,
            priority_delay_multiplier=priority_multiplier,
        )


@dataclass(frozen=True, slots=True)
class SettledSegmentExperience:
    """The completed (s, a, r) part awaiting the same node's next state."""

    reward_input: SegmentRewardInput
    reward_breakdown: RewardBreakdown

    @property
    def node_id(self) -> int:
        return self.reward_input.decision.node_id

    @property
    def decision(self) -> SegmentActionDecision:
        return self.reward_input.decision

    @property
    def settled_at(self) -> float:
        return self.reward_input.settled_at


@dataclass(frozen=True, slots=True)
class QTransition:
    transition_id: str
    node_id: int
    decision_id: str
    state: RLState
    action_index: int
    current_remaining_hops: int
    reward: float
    next_state: RLState | None
    next_remaining_hops: int | None
    terminal: bool
    settled_at: float
    next_observed_at: float | None
    terminal_reason: str = ""
    transition_scope: str = TRANSITION_SCOPE
    next_state_scope: str = NEXT_STATE_SCOPE

    def __post_init__(self) -> None:
        if not self.transition_id:
            raise ValueError("transition_id cannot be empty.")
        if self.node_id < 0:
            raise ValueError("node_id cannot be negative.")
        if not self.decision_id:
            raise ValueError("decision_id cannot be empty.")
        if self.current_remaining_hops <= 0:
            raise ValueError("current_remaining_hops must be positive.")
        _require_finite(self.reward, name="reward")
        settled = _require_finite(self.settled_at, name="settled_at")
        if settled < 0:
            raise ValueError("settled_at cannot be negative.")
        if self.terminal:
            if self.next_state is not None or self.next_remaining_hops is not None:
                raise ValueError("Terminal transitions cannot carry a bootstrap state.")
            if self.next_observed_at is not None:
                raise ValueError("Terminal transitions cannot carry next_observed_at.")
            if not self.terminal_reason:
                raise ValueError("Terminal transitions require terminal_reason.")
        else:
            if self.next_state is None or self.next_remaining_hops is None:
                raise ValueError("Non-terminal transitions require next_state and hops.")
            if self.next_remaining_hops <= 0:
                raise ValueError("next_remaining_hops must be positive.")
            if self.next_observed_at is None:
                raise ValueError("Non-terminal transitions require next_observed_at.")
            observed = _require_finite(self.next_observed_at, name="next_observed_at")
            if observed < settled:
                raise ValueError("The next local decision cannot precede settlement.")
            if self.terminal_reason:
                raise ValueError("Non-terminal transitions cannot carry terminal_reason.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "node_id": self.node_id,
            "decision_id": self.decision_id,
            "state": list(self.state.as_tuple()),
            "action_index": self.action_index,
            "current_remaining_hops": self.current_remaining_hops,
            "reward": self.reward,
            "next_state": None if self.next_state is None else list(self.next_state.as_tuple()),
            "next_remaining_hops": self.next_remaining_hops,
            "terminal": self.terminal,
            "settled_at": self.settled_at,
            "next_observed_at": self.next_observed_at,
            "terminal_reason": self.terminal_reason,
            "transition_scope": self.transition_scope,
            "next_state_scope": self.next_state_scope,
        }


class LocalTransitionAssembler:
    """Pair a settled local segment with that node's next decision epoch."""

    def __init__(self, reward_model: LocalSegmentReward | None = None) -> None:
        self.reward_model = reward_model or LocalSegmentReward()
        self._pending: dict[int, SettledSegmentExperience] = {}
        self._transition_sequence: dict[int, int] = {}

    def settle(self, item: SegmentRewardInput) -> SettledSegmentExperience:
        node_id = item.decision.node_id
        if node_id in self._pending:
            raise RuntimeError(
                "A node already has a settled segment awaiting its next local decision."
            )
        experience = SettledSegmentExperience(
            reward_input=item,
            reward_breakdown=self.reward_model.calculate(item),
        )
        self._pending[node_id] = experience
        return experience

    def has_pending(self, node_id: int) -> bool:
        return node_id in self._pending

    def complete_with_next_state(
        self,
        *,
        node_id: int,
        next_state: RLState,
        next_remaining_hops: int,
        observed_at: float,
    ) -> QTransition:
        experience = self._pop_pending(node_id)
        return self._make_transition(
            experience,
            next_state=next_state,
            next_remaining_hops=next_remaining_hops,
            terminal=False,
            next_observed_at=observed_at,
            terminal_reason="",
        )

    def finalize_terminal(
        self,
        *,
        node_id: int,
        terminal_at: float,
        reason: str,
    ) -> QTransition:
        experience = self._pop_pending(node_id)
        terminal_time = _require_finite(terminal_at, name="terminal_at")
        if terminal_time < experience.settled_at:
            raise ValueError("terminal_at cannot precede segment settlement.")
        if not reason:
            raise ValueError("A terminal transition requires a reason.")
        return self._make_transition(
            experience,
            next_state=None,
            next_remaining_hops=None,
            terminal=True,
            next_observed_at=None,
            terminal_reason=reason,
        )

    def _pop_pending(self, node_id: int) -> SettledSegmentExperience:
        try:
            return self._pending.pop(node_id)
        except KeyError as exc:
            raise KeyError("No settled segment is pending for this node.") from exc

    def _make_transition(
        self,
        experience: SettledSegmentExperience,
        *,
        next_state: RLState | None,
        next_remaining_hops: int | None,
        terminal: bool,
        next_observed_at: float | None,
        terminal_reason: str,
    ) -> QTransition:
        node_id = experience.node_id
        sequence = self._transition_sequence.get(node_id, 0) + 1
        self._transition_sequence[node_id] = sequence
        decision = experience.decision
        return QTransition(
            transition_id=f"node-{node_id}:transition-{sequence}",
            node_id=node_id,
            decision_id=decision.decision_id,
            state=decision.state,
            action_index=decision.action_index,
            current_remaining_hops=decision.remaining_hops,
            reward=experience.reward_breakdown.reward,
            next_state=next_state,
            next_remaining_hops=next_remaining_hops,
            terminal=terminal,
            settled_at=experience.settled_at,
            next_observed_at=next_observed_at,
            terminal_reason=terminal_reason,
        )


@dataclass(frozen=True, slots=True)
class QLearningConfig:
    alpha: float = 0.20
    gamma: float = 0.90

    def __post_init__(self) -> None:
        alpha = _require_finite(self.alpha, name="alpha")
        gamma = _require_finite(self.gamma, name="gamma")
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be within (0, 1].")
        if not 0.0 <= gamma <= 1.0:
            raise ValueError("gamma must be within [0, 1].")


@dataclass(frozen=True, slots=True)
class QUpdateResult:
    transition_id: str
    node_id: int
    state: RLState
    action_index: int
    old_q: float
    reward: float
    bootstrap_value: float
    target: float
    td_error: float
    new_q: float
    alpha: float
    gamma: float
    terminal: bool
    legal_next_action_indices: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "node_id": self.node_id,
            "state": list(self.state.as_tuple()),
            "action_index": self.action_index,
            "old_q": self.old_q,
            "reward": self.reward,
            "bootstrap_value": self.bootstrap_value,
            "target": self.target,
            "td_error": self.td_error,
            "new_q": self.new_q,
            "alpha": self.alpha,
            "gamma": self.gamma,
            "terminal": self.terminal,
            "legal_next_action_indices": list(self.legal_next_action_indices),
        }


class LocalTabularQLearner:
    """Apply off-policy Q-learning to exactly one node-owned sparse Q table."""

    def __init__(
        self,
        *,
        node_id: int,
        q_table: SparseLocalQTable,
        action_space: JointActionSpace | None = None,
        config: QLearningConfig | None = None,
    ) -> None:
        if node_id < 0:
            raise ValueError("node_id cannot be negative.")
        self.node_id = node_id
        self.action_space = action_space or JointActionSpace()
        self.config = config or QLearningConfig()
        self.q_table = q_table
        if q_table.node_id != node_id:
            raise ValueError("A learner cannot update another node's local Q table.")
        if q_table.action_count != len(self.action_space.actions):
            raise ValueError("Q table action_count must match the frozen action space.")

    def update(self, transition: QTransition) -> QUpdateResult:
        if transition.node_id != self.node_id:
            raise ValueError("Transition node_id does not match this local learner.")
        action = self.action_space.index_to_action(transition.action_index)
        self.action_space.validate_action(
            action, remaining_hops=transition.current_remaining_hops
        )
        old_q = self.q_table.get(transition.state, transition.action_index)

        if transition.terminal:
            legal_next: tuple[int, ...] = ()
            bootstrap = 0.0
        else:
            assert transition.next_state is not None
            assert transition.next_remaining_hops is not None
            legal_next = self.action_space.valid_action_indices(
                transition.next_remaining_hops
            )
            bootstrap = max(
                self.q_table.get(transition.next_state, index)
                for index in legal_next
            )

        target = transition.reward + self.config.gamma * bootstrap
        td_error = target - old_q
        new_q = old_q + self.config.alpha * td_error
        for name, value in (
            ("old_q", old_q),
            ("bootstrap", bootstrap),
            ("target", target),
            ("td_error", td_error),
            ("new_q", new_q),
        ):
            _require_finite(value, name=name)
        self.q_table.set_value(transition.state, transition.action_index, new_q)
        return QUpdateResult(
            transition_id=transition.transition_id,
            node_id=self.node_id,
            state=transition.state,
            action_index=transition.action_index,
            old_q=old_q,
            reward=transition.reward,
            bootstrap_value=bootstrap,
            target=target,
            td_error=td_error,
            new_q=new_q,
            alpha=self.config.alpha,
            gamma=self.config.gamma,
            terminal=transition.terminal,
            legal_next_action_indices=legal_next,
        )


__all__ = [
    "LocalSegmentReward",
    "LocalTabularQLearner",
    "LocalTransitionAssembler",
    "NEXT_STATE_SCOPE",
    "QLearningConfig",
    "QTransition",
    "QUpdateResult",
    "REWARD_DESIGN_VERSION",
    "RewardBreakdown",
    "RewardConfig",
    "SegmentRewardInput",
    "SegmentSettlement",
    "SettledSegmentExperience",
    "TRANSITION_SCOPE",
    "UPDATE_DESIGN_VERSION",
]
