"""Day17: integrate Day14-Day16 local RL interfaces into Day13 Fixed-PRMAC.

Frozen inheritance
------------------
- Day13 remains the event-driven, multi-segment Fixed-PRMAC lifecycle.
- Day14 ``LocalObservation -> RLState`` is used unchanged.
- Day15 selects one ``JointAction(K, CW)`` at the local FIFO head before the
  initial DIFS/backoff; the action is held for the complete retry sequence.
- Day16 settles one local reward per complete reservation segment and updates
  only the segment-start node's sparse Q table.

Day17 deliberately does not add a centralized scheduler, global state, per-hop
re-decisions, re-decisions after PR_NACK, a complete training campaign, or a
large-scale hyperparameter search.  The Python simulator is centralized as an
event executor, while protocol decisions, histories, Q tables, and updates are
logically node-local.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import random
import sys
from typing import Any, Callable

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY16_CODE = DAILY_DIR / "Day16_奖励函数与更新机制" / "code"
DAY15_CODE = DAILY_DIR / "Day15_Q-learning动作与策略" / "code"
DAY14_CODE = DAILY_DIR / "Day14_Q-learning状态设计" / "code"
DAY13_CODE = DAILY_DIR / "Day13_Fixed-PRMAC验证" / "code"
DAY12_CODE = DAILY_DIR / "Day12_Fixed-PRMAC失败与重传" / "code"
DAY11_CODE = DAILY_DIR / "Day11_Fixed-PRMAC连续转发" / "code"
DAY10_CODE = DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

_import_paths = [
    CURRENT_DIR,
    DAY16_CODE,
    DAY15_CODE,
    DAY14_CODE,
    DAY13_CODE,
    DAY12_CODE,
    DAY11_CODE,
    DAY10_CODE,
    DAY09_CODE,
    DAY03_CODE,
]
for path in _import_paths:
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from fixed_prmac_end_to_end import (  # type: ignore  # noqa: E402
    Day13FixedPRMACConfig,
    Day13FixedPRMACMetrics,
    EndToEndRecord,
    EndToEndSegmentRecord,
    EndToEndSegmentStatus,
    EndToEndStatus,
    FixedPRMACEndToEndController,
)
from fixed_prmac_messages import (  # type: ignore  # noqa: E402
    PRMACFrame,
    PRMACFrameType,
    ReservationRecord,
    ReservationStatus,
    ReservedLink,
)
from fixed_prmac_retry import (  # type: ignore  # noqa: E402
    Day12ReservationTable,
    FixedPRMACRetryController,
    ReservationRetryAttempt,
    ReservationRetryRecord,
    ReservationRetryStatus,
)
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from rl_prmac_state import LocalObservation, RLState, StateEncoder  # noqa: E402
from rl_prmac_action_policy import (  # noqa: E402
    ACTION_DESIGN_VERSION,
    JointAction,
    JointActionSpace,
    LocalEpsilonGreedyPolicy,
    SegmentActionDecision,
    SelectionMode,
    SparseLocalQTable,
)
from rl_prmac_reward_update import (  # noqa: E402
    LocalSegmentReward,
    LocalTabularQLearner,
    LocalTransitionAssembler,
    QLearningConfig,
    QTransition,
    QUpdateResult,
    REWARD_DESIGN_VERSION,
    RewardBreakdown,
    RewardConfig,
    SegmentRewardInput,
    SegmentSettlement,
    UPDATE_DESIGN_VERSION,
)

PROTOCOL_INTEGRATION_VERSION = "Day17-Final-distributed-controller-integration-v1"
DECISION_EPOCH = "local_fifo_head_before_initial_difs_and_backoff"
ACTION_LIFETIME = "one_complete_segment_retry_sequence"
LOCAL_NEXT_STATE_RULE = "same_node_next_local_decision_epoch"

BusyRatioProvider = Callable[[int, float], float | None]
SegmentMapping = tuple[str, int]


def _mean(values: deque[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _require_finite(value: float, *, name: str) -> float:
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ValueError(f"{name} must be finite.")
    return resolved


@dataclass(frozen=True, slots=True)
class Day17RLPRMACConfig(Day13FixedPRMACConfig):
    """Day13 event parameters plus local Day15/Day16 learning parameters.

    ``fixed_k`` and ``fixed_cw_min`` remain inherited only for compatibility
    with the Day13 baseline and external blocker reservations.  RL-controlled
    packet segments use their explicit Day15 action and never mutate these
    shared configuration fields.
    """

    epsilon: float = 0.10
    learning_alpha: float = 0.20
    learning_gamma: float = 0.90
    recent_retry_window: int = 8
    node_seed_stride: int = 1009
    policy_seed_offset: int = 17_017
    contention_seed_offset: int = 27_017

    def __post_init__(self) -> None:
        Day13FixedPRMACConfig.__post_init__(self)
        epsilon = _require_finite(self.epsilon, name="epsilon")
        alpha = _require_finite(self.learning_alpha, name="learning_alpha")
        gamma = _require_finite(self.learning_gamma, name="learning_gamma")
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon must be within [0, 1].")
        if not 0.0 < alpha <= 1.0:
            raise ValueError("learning_alpha must be within (0, 1].")
        if not 0.0 <= gamma <= 1.0:
            raise ValueError("learning_gamma must be within [0, 1].")
        if self.recent_retry_window <= 0:
            raise ValueError("recent_retry_window must be positive.")
        if self.node_seed_stride <= 0:
            raise ValueError("node_seed_stride must be positive.")
        if self.policy_seed_offset < 0 or self.contention_seed_offset < 0:
            raise ValueError("Seed offsets cannot be negative.")
        if not self.initial_access_enabled:
            raise ValueError(
                "Day17 requires the initial DIFS/backoff decision boundary."
            )


@dataclass(slots=True)
class Day17RLPRMACMetrics(Day13FixedPRMACMetrics):
    local_agents_created: int = 0
    rl_decisions: int = 0
    exploration_decisions: int = 0
    exploitation_decisions: int = 0
    rl_segments_settled: int = 0
    rl_successful_segments: int = 0
    rl_failed_segments: int = 0
    q_updates: int = 0
    terminal_q_updates: int = 0
    bootstrapped_q_updates: int = 0
    selected_action_counts: dict[str, int] = field(default_factory=dict)
    selected_k_counts: dict[int, int] = field(default_factory=dict)
    selected_cw_counts: dict[int, int] = field(default_factory=dict)
    settled_rewards: list[float] = field(default_factory=list)
    td_errors: list[float] = field(default_factory=list)

    def record_decision(self, decision: SegmentActionDecision) -> None:
        self.rl_decisions += 1
        if decision.selection_mode == SelectionMode.EXPLORE:
            self.exploration_decisions += 1
        else:
            self.exploitation_decisions += 1
        action_key = f"K={decision.action.reservation_length_k},CW={decision.action.initial_cw}"
        self.selected_action_counts[action_key] = (
            self.selected_action_counts.get(action_key, 0) + 1
        )
        k = decision.action.reservation_length_k
        cw = decision.action.initial_cw
        self.selected_k_counts[k] = self.selected_k_counts.get(k, 0) + 1
        self.selected_cw_counts[cw] = self.selected_cw_counts.get(cw, 0) + 1

    def record_settlement(
        self,
        settlement: SegmentSettlement,
        reward: RewardBreakdown,
    ) -> None:
        self.rl_segments_settled += 1
        if settlement == SegmentSettlement.SUCCESS:
            self.rl_successful_segments += 1
        else:
            self.rl_failed_segments += 1
        self.settled_rewards.append(float(reward.reward))

    def record_update(self, update: QUpdateResult) -> None:
        self.q_updates += 1
        if update.terminal:
            self.terminal_q_updates += 1
        else:
            self.bootstrapped_q_updates += 1
        self.td_errors.append(float(update.td_error))

    def summary(self, table: Day12ReservationTable) -> dict[str, Any]:
        payload = Day13FixedPRMACMetrics.summary(self, table)
        payload.update(
            {
                "local_agents_created": self.local_agents_created,
                "rl_decisions": self.rl_decisions,
                "exploration_decisions": self.exploration_decisions,
                "exploitation_decisions": self.exploitation_decisions,
                "rl_segments_settled": self.rl_segments_settled,
                "rl_successful_segments": self.rl_successful_segments,
                "rl_failed_segments": self.rl_failed_segments,
                "q_updates": self.q_updates,
                "terminal_q_updates": self.terminal_q_updates,
                "bootstrapped_q_updates": self.bootstrapped_q_updates,
                "selected_action_counts": dict(self.selected_action_counts),
                "selected_k_counts": dict(self.selected_k_counts),
                "selected_cw_counts": dict(self.selected_cw_counts),
                "average_settled_reward": (
                    sum(self.settled_rewards) / len(self.settled_rewards)
                    if self.settled_rewards
                    else 0.0
                ),
                "average_absolute_td_error": (
                    sum(abs(value) for value in self.td_errors) / len(self.td_errors)
                    if self.td_errors
                    else 0.0
                ),
            }
        )
        return payload


@dataclass(slots=True)
class LocalNodeAgent:
    """One logically distributed node-local policy, history, and Q learner."""

    node_id: int
    action_space: JointActionSpace
    state_encoder: StateEncoder
    q_table: SparseLocalQTable
    policy: LocalEpsilonGreedyPolicy
    learner: LocalTabularQLearner
    transition_assembler: LocalTransitionAssembler
    contention_rng: random.Random
    recent_retry_window: int
    last_reservation_succeeded: bool | None = None
    recent_retries: deque[int] = field(default_factory=deque)
    transitions: list[QTransition] = field(default_factory=list)
    updates: list[QUpdateResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.node_id < 0:
            raise ValueError("node_id cannot be negative.")
        if self.q_table.node_id != self.node_id:
            raise ValueError("A local agent must own its Q table.")
        if self.recent_retry_window <= 0:
            raise ValueError("recent_retry_window must be positive.")
        if self.recent_retries.maxlen != self.recent_retry_window:
            self.recent_retries = deque(
                self.recent_retries,
                maxlen=self.recent_retry_window,
            )

    @property
    def recent_mean_retries(self) -> float:
        return float(_mean(self.recent_retries))

    @property
    def has_pending_experience(self) -> bool:
        return self.transition_assembler.has_pending(self.node_id)

    def record_local_outcome(self, *, succeeded: bool, retries_used: int) -> None:
        if retries_used < 0:
            raise ValueError("retries_used cannot be negative.")
        self.last_reservation_succeeded = bool(succeeded)
        self.recent_retries.append(int(retries_used))

    def complete_pending_with_next_state(
        self,
        *,
        next_state: RLState,
        next_remaining_hops: int,
        observed_at: float,
    ) -> tuple[QTransition, QUpdateResult] | None:
        if not self.has_pending_experience:
            return None
        transition = self.transition_assembler.complete_with_next_state(
            node_id=self.node_id,
            next_state=next_state,
            next_remaining_hops=next_remaining_hops,
            observed_at=observed_at,
        )
        update = self.learner.update(transition)
        self.transitions.append(transition)
        self.updates.append(update)
        return transition, update

    def settle(
        self,
        item: SegmentRewardInput,
        *,
        terminal_reason: str | None = None,
    ) -> tuple[RewardBreakdown, QTransition | None, QUpdateResult | None]:
        experience = self.transition_assembler.settle(item)
        reward = experience.reward_breakdown
        if terminal_reason is None:
            return reward, None, None
        transition = self.transition_assembler.finalize_terminal(
            node_id=self.node_id,
            terminal_at=item.settled_at,
            reason=terminal_reason,
        )
        update = self.learner.update(transition)
        self.transitions.append(transition)
        self.updates.append(update)
        return reward, transition, update

    def finalize_pending(
        self,
        *,
        terminal_at: float,
        reason: str,
    ) -> tuple[QTransition, QUpdateResult] | None:
        if not self.has_pending_experience:
            return None
        transition = self.transition_assembler.finalize_terminal(
            node_id=self.node_id,
            terminal_at=terminal_at,
            reason=reason,
        )
        update = self.learner.update(transition)
        self.transitions.append(transition)
        self.updates.append(update)
        return transition, update

    def snapshot(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "last_reservation_succeeded": self.last_reservation_succeeded,
            "recent_retries": list(self.recent_retries),
            "recent_mean_retries": self.recent_mean_retries,
            "q_entry_count": self.q_table.entry_count,
            "pending_experience": self.has_pending_experience,
            "transition_count": len(self.transitions),
            "update_count": len(self.updates),
        }


@dataclass(slots=True)
class SegmentRLContext:
    """Auditable bridge between a Day13 segment and Day14-Day16 objects."""

    session_id: str
    segment_index: int
    node_id: int
    packet_id: int
    flow_id: str
    observation: LocalObservation
    state: RLState
    decision: SegmentActionDecision
    retry_id: str | None = None
    reward_input: SegmentRewardInput | None = None
    reward_breakdown: RewardBreakdown | None = None
    transition: QTransition | None = None
    update: QUpdateResult | None = None
    status: str = "DECIDED"

    @property
    def mapping(self) -> SegmentMapping:
        return (self.session_id, self.segment_index)

    def as_dict(self) -> dict[str, Any]:
        observation = asdict(self.observation)
        return {
            "session_id": self.session_id,
            "segment_index": self.segment_index,
            "node_id": self.node_id,
            "packet_id": self.packet_id,
            "flow_id": self.flow_id,
            "observation": observation,
            "state": list(self.state.as_tuple()),
            "decision": self.decision.as_dict(),
            "retry_id": self.retry_id,
            "reward_input": (
                None
                if self.reward_input is None
                else {
                    "packet_id": self.reward_input.packet_id,
                    "flow_id": self.reward_input.flow_id,
                    "priority": self.reward_input.priority,
                    "queue_delay": self.reward_input.queue_delay,
                    "settled_at": self.reward_input.settled_at,
                    "settlement": self.reward_input.settlement.value,
                    "effective_hops": self.reward_input.effective_hops,
                    "retries_used": self.reward_input.retries_used,
                    "retry_limit": self.reward_input.retry_limit,
                    "pr_nack_count": self.reward_input.pr_nack_count,
                    "control_bytes": self.reward_input.control_bytes,
                    "payload_bytes": self.reward_input.payload_bytes,
                    "packet_delivered": self.reward_input.packet_delivered,
                    "failure_reason": self.reward_input.failure_reason,
                    "service_delay": self.reward_input.service_delay,
                }
            ),
            "reward_breakdown": (
                None
                if self.reward_breakdown is None
                else self.reward_breakdown.as_dict()
            ),
            "transition": None if self.transition is None else self.transition.as_dict(),
            "update": None if self.update is None else self.update.as_dict(),
            "status": self.status,
        }


class RLPRMACProtocolController(FixedPRMACEndToEndController):
    """Day13 end-to-end controller with node-local Day14-Day16 decisions."""

    PRIORITY_SEGMENT_ACCESS_COMPLETE = 40

    def __init__(
        self,
        *,
        simulator: Simulator,
        config: Day17RLPRMACConfig | None = None,
        adjacency: dict[int, set[int]] | None = None,
        table: Day12ReservationTable | None = None,
        metrics: Day17RLPRMACMetrics | None = None,
        action_space: JointActionSpace | None = None,
        state_encoder: StateEncoder | None = None,
        reward_config: RewardConfig | None = None,
        busy_ratio_provider: BusyRatioProvider | None = None,
    ) -> None:
        resolved_config = config or Day17RLPRMACConfig()
        resolved_metrics = metrics or Day17RLPRMACMetrics()
        super().__init__(
            simulator=simulator,
            config=resolved_config,
            adjacency=adjacency,
            table=table,
            metrics=resolved_metrics,
        )
        self.action_space = action_space or JointActionSpace(
            cw_max=resolved_config.cw_max,
            slot_time=resolved_config.slot_time,
            difs_time=resolved_config.difs_time,
        )
        expected_actions = (
            (1, 15),
            (1, 31),
            (2, 15),
            (2, 31),
            (3, 15),
            (3, 31),
        )
        if tuple(action.as_tuple() for action in self.action_space.actions) != expected_actions:
            raise ValueError("Day17 must preserve the frozen Day15 six-action catalog.")
        self.state_encoder = state_encoder or StateEncoder()
        self.reward_model = LocalSegmentReward(
            config=reward_config,
            action_space=self.action_space,
        )
        self.busy_ratio_provider = busy_ratio_provider
        self._agents: dict[int, LocalNodeAgent] = {}
        self._segment_contexts: dict[SegmentMapping, SegmentRLContext] = {}
        self._contexts_by_decision_id: dict[str, SegmentRLContext] = {}
        self._decision_by_retry_id: dict[str, SegmentActionDecision] = {}
        self._mapping_by_retry_id: dict[str, SegmentMapping] = {}

    @property
    def config(self) -> Day17RLPRMACConfig:
        return self._config

    @config.setter
    def config(self, value: Day17RLPRMACConfig) -> None:
        self._config = value

    @property
    def metrics(self) -> Day17RLPRMACMetrics:
        return self._metrics

    @metrics.setter
    def metrics(self, value: Day17RLPRMACMetrics) -> None:
        self._metrics = value

    def local_agent(self, node_id: int) -> LocalNodeAgent:
        """Return/create exactly one independent learning agent for a node."""
        if node_id < 0:
            raise ValueError("node_id cannot be negative.")
        existing = self._agents.get(node_id)
        if existing is not None:
            return existing
        q_table = SparseLocalQTable(
            node_id=node_id,
            action_count=len(self.action_space.actions),
        )
        policy_seed = (
            self.config.random_seed
            + self.config.policy_seed_offset
            + node_id * self.config.node_seed_stride
        )
        contention_seed = (
            self.config.random_seed
            + self.config.contention_seed_offset
            + node_id * self.config.node_seed_stride
        )
        policy = LocalEpsilonGreedyPolicy(
            node_id=node_id,
            action_space=self.action_space,
            q_table=q_table,
            epsilon=self.config.epsilon,
            random_seed=policy_seed,
        )
        learner = LocalTabularQLearner(
            node_id=node_id,
            q_table=q_table,
            action_space=self.action_space,
            config=QLearningConfig(
                alpha=self.config.learning_alpha,
                gamma=self.config.learning_gamma,
            ),
        )
        agent = LocalNodeAgent(
            node_id=node_id,
            action_space=self.action_space,
            state_encoder=self.state_encoder,
            q_table=q_table,
            policy=policy,
            learner=learner,
            transition_assembler=LocalTransitionAssembler(self.reward_model),
            contention_rng=random.Random(contention_seed),
            recent_retry_window=self.config.recent_retry_window,
            recent_retries=deque(maxlen=self.config.recent_retry_window),
        )
        self._agents[node_id] = agent
        self.metrics.local_agents_created += 1
        return agent

    def segment_context(
        self,
        session_id: str,
        segment_index: int,
    ) -> SegmentRLContext:
        try:
            return self._segment_contexts[(session_id, segment_index)]
        except KeyError as exc:
            raise KeyError("Unknown Day17 segment context.") from exc

    def _try_start_node_queue(self, node_id: int) -> None:
        """Select one local action after FIFO service begins, before DIFS/backoff."""
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
            if not queue:
                self._segment_queues.pop(node_id, None)
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

        agent = self.local_agent(node_id)
        busy_ratio = self._local_busy_ratio(node_id)
        observation = LocalObservation(
            node_id=node_id,
            packet_id=int(packet.packet_id),
            flow_id=record.flow_id,
            observed_at=self.now,
            remaining_hops=int(packet.remaining_hops),
            local_queue_length=len(queue),
            queue_limit=self.config.queue_limit,
            priority=int(packet.priority),
            last_reservation_succeeded=agent.last_reservation_succeeded,
            recent_mean_retries=agent.recent_mean_retries,
            channel_busy_ratio=busy_ratio,
        )
        state = self.state_encoder.encode(observation)

        completed_previous = agent.complete_pending_with_next_state(
            next_state=state,
            next_remaining_hops=int(packet.remaining_hops),
            observed_at=self.now,
        )
        if completed_previous is not None:
            transition, update = completed_previous
            self._attach_update(transition, update)

        decision = agent.policy.select_action(
            state=state,
            remaining_hops=int(packet.remaining_hops),
            selected_at=self.now,
        )
        if decision.node_id != node_id:
            raise RuntimeError("A node-local policy returned another node's decision.")
        self.action_space.validate_action(
            decision.action,
            remaining_hops=int(packet.remaining_hops),
        )
        context = SegmentRLContext(
            session_id=session_id,
            segment_index=segment_index,
            node_id=node_id,
            packet_id=int(packet.packet_id),
            flow_id=record.flow_id,
            observation=observation,
            state=state,
            decision=decision,
        )
        self._segment_contexts[mapping] = context
        self._contexts_by_decision_id[decision.decision_id] = context
        self.metrics.record_decision(decision)

        backoff_slots = self.action_space.sample_backoff_slots(
            decision.action,
            retry_number=0,
            rng=agent.contention_rng,
        )
        access_delay = self.action_space.access_delay(backoff_slots)
        segment.access_cw = decision.action.initial_cw
        segment.access_backoff_slots = backoff_slots
        segment.access_delay = access_delay
        segment.status = EndToEndSegmentStatus.ACCESS_BACKOFF
        self.metrics.initial_access_backoff_slots += backoff_slots
        self.metrics.initial_access_delays.append(access_delay)
        self._trace_e2e(
            "RL_SEGMENT_DECISION",
            record,
            packet,
            segment_number=segment.segment_number,
            detail=(
                f"decision_id={decision.decision_id}, "
                f"state={state.as_tuple()}, action={decision.action.as_tuple()}, "
                f"selection_mode={decision.selection_mode.value}, "
                f"legal_actions={decision.legal_action_indices}"
            ),
        )
        self._trace_e2e(
            "SEGMENT_ACCESS_BACKOFF",
            record,
            packet,
            segment_number=segment.segment_number,
            detail=(
                f"segment_start_index={segment.segment_start_index}, "
                f"queue_delay={segment.queue_delay:.9f}s, "
                f"cw={segment.access_cw}, backoff_slots={backoff_slots}, "
                f"access_delay={access_delay:.9f}s, decision_id={decision.decision_id}"
            ),
        )
        self.simulator.schedule(
            access_delay,
            lambda: self._start_segment_retry(record, packet, segment),
            event_type="SEGMENT_ACCESS_COMPLETE",
            priority=self.PRIORITY_SEGMENT_ACCESS_COMPLETE,
        )

    def _local_busy_ratio(self, node_id: int) -> float | None:
        if self.busy_ratio_provider is None:
            return None
        value = self.busy_ratio_provider(node_id, self.now)
        if value is None:
            return None
        resolved = _require_finite(value, name="channel_busy_ratio")
        if not 0.0 <= resolved <= 1.0:
            raise ValueError("channel_busy_ratio must be within [0, 1].")
        return resolved

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
        mapping = (record.session_id, segment.segment_number - 1)
        context = self._segment_contexts.get(mapping)
        if context is None:
            raise RuntimeError("Day17 segment cannot start without a local decision.")
        segment.access_completed_at = self.now
        segment.status = EndToEndSegmentStatus.RESERVING
        retry_id = self.schedule_reservation_with_retry(
            packet,
            flow_id=record.flow_id,
            at=self.now,
            decision=context.decision,
        )
        segment.retry_id = retry_id
        context.retry_id = retry_id
        self._retry_to_segment[retry_id] = mapping
        self._mapping_by_retry_id[retry_id] = mapping
        self._trace_e2e(
            "SEGMENT_RESERVATION_START",
            record,
            packet,
            segment_number=segment.segment_number,
            detail=(
                f"retry_id={retry_id}, decision_id={context.decision.decision_id}, "
                f"action={context.decision.action.as_tuple()}"
            ),
        )

    def schedule_reservation_with_retry(
        self,
        packet: Packet,
        *,
        flow_id: str | None = None,
        at: float | None = None,
        decision: SegmentActionDecision | None = None,
    ) -> str:
        """Create one retry sequence bound to one already selected Day15 action."""
        resolved_decision = decision or self._active_decision_for_packet(packet)
        if resolved_decision.node_id != int(packet.current_node):
            raise ValueError("The retry sequence decision must belong to its start node.")
        self.action_space.validate_action(
            resolved_decision.action,
            remaining_hops=int(packet.remaining_hops),
        )
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
        self._decision_by_retry_id[retry_id] = resolved_decision
        self.simulator.schedule_at(
            sequence_time,
            lambda: self._begin_retry_sequence(retry_record, packet),
            event_type="RETRY_SEQUENCE_START",
            priority=self.PRIORITY_RETRY_SEQUENCE_START,
        )
        return retry_id

    def _active_decision_for_packet(self, packet: Packet) -> SegmentActionDecision:
        node_id = int(packet.current_node)
        mapping = self._active_segment_by_node.get(node_id)
        if mapping is None:
            raise RuntimeError("No active local segment decision exists for this packet.")
        context = self._segment_contexts.get(mapping)
        if context is None or context.packet_id != int(packet.packet_id):
            raise RuntimeError("Active segment decision does not match this packet.")
        return context.decision

    def _begin_retry_sequence(
        self,
        retry_record: ReservationRetryRecord,
        packet: Packet,
    ) -> None:
        if retry_record.status != ReservationRetryStatus.SCHEDULED:
            return
        decision = self._decision_for_retry(retry_record.retry_id)
        retry_record.status = ReservationRetryStatus.ATTEMPTING
        retry_record.started_at = self.now
        self.metrics.retry_sequences_started += 1
        self._schedule_attempt(
            retry_record,
            packet,
            attempt_number=1,
            contention_window=decision.action.initial_cw,
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
        decision = self._decision_for_retry(retry_record.retry_id)
        reservation_id = self._schedule_action_reservation(
            packet,
            flow_id=retry_record.flow_id,
            at=self.now,
            decision=decision,
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
                    f"retry_limit={retry_record.retry_limit}, "
                    f"decision_id={decision.decision_id}"
                ),
            )
        self._trace(
            "RETRY_ATTEMPT_SCHEDULED",
            reservation,
            node_id=reservation.initiator,
            detail=(
                f"retry_id={retry_record.retry_id}, attempt={attempt_number}, "
                f"cw={contention_window}, "
                f"backoff_slots={backoff_slots if backoff_slots is not None else 0}, "
                f"backoff_delay={backoff_delay:.9f}s, "
                f"action={decision.action.as_tuple()}"
            ),
        )
        return reservation_id

    def _schedule_action_reservation(
        self,
        packet: Packet,
        *,
        flow_id: str,
        at: float,
        decision: SegmentActionDecision,
    ) -> str:
        request_time = float(at)
        if request_time < self.now:
            raise ValueError("Reservation cannot be scheduled in the past.")
        route = tuple(int(node_id) for node_id in packet.route)
        if len(route) < 2:
            raise ValueError("RL-PRMAC requires a path with at least one hop.")
        start_index = int(packet.current_hop_index)
        if not 0 <= start_index < len(route) - 1:
            raise ValueError("Packet must have at least one remaining hop to reserve.")
        if int(packet.current_node) != route[start_index]:
            raise RuntimeError("Packet current node is inconsistent with route.")
        remaining_hops = len(route) - 1 - start_index
        self.action_space.validate_action(
            decision.action,
            remaining_hops=remaining_hops,
        )
        effective_hops = decision.action.reservation_length_k
        links = tuple(
            ReservedLink(route[index], route[index + 1])
            for index in range(start_index, start_index + effective_hops)
        )
        self._validate_links(links)

        self._reservation_sequence += 1
        reservation_id = (
            f"{flow_id}:packet-{packet.packet_id}:segment-{start_index}:"
            f"request-{self._reservation_sequence}"
        )
        record = ReservationRecord(
            reservation_id=reservation_id,
            flow_id=flow_id,
            packet_id=int(packet.packet_id),
            path=route,
            segment_start_index=start_index,
            requested_hops=effective_hops,
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

    def _decision_for_retry(self, retry_id: str) -> SegmentActionDecision:
        try:
            return self._decision_by_retry_id[retry_id]
        except KeyError as exc:
            raise KeyError("Retry sequence has no frozen Day15 action.") from exc

    def _handle_rejected_attempt(
        self,
        retry_record: ReservationRetryRecord,
        *,
        packet: Packet,
        record: ReservationRecord,
    ) -> None:
        """Use BEB rooted at the selected initial CW; never re-select an action."""
        attempt = self._attempt_by_reservation_id[record.reservation_id]
        decision = self._decision_for_retry(retry_record.retry_id)
        retries_already_used = attempt.attempt_number - 1
        if retries_already_used >= retry_record.retry_limit:
            final_reason = (
                f"retry_limit_exhausted={retry_record.retry_limit}; "
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
                    f"completion_delay={delay:.9f}s; {final_reason}; "
                    f"decision_id={decision.decision_id}"
                ),
            )
            self._settle_failed_segment(
                retry_record=retry_record,
                packet=packet,
                final_reason=final_reason,
            )
            return

        retry_number = attempt.attempt_number
        next_cw = self.action_space.contention_window_for_retry(
            decision.action,
            retry_number,
        )
        agent = self.local_agent(decision.node_id)
        backoff_slots = agent.contention_rng.randint(0, next_cw)
        backoff_delay = self.action_space.access_delay(backoff_slots)
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
                f"backoff_delay={backoff_delay:.9f}s, "
                f"action_held={decision.action.as_tuple()}"
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

    def _settle_failed_segment(
        self,
        *,
        retry_record: ReservationRetryRecord,
        packet: Packet,
        final_reason: str,
    ) -> None:
        mapping = self._retry_to_segment.get(retry_record.retry_id)
        if mapping is None:
            return
        session_id, segment_index = mapping
        e2e = self.end_to_end_records[session_id]
        segment = e2e.segments[segment_index]
        segment.status = EndToEndSegmentStatus.FAILED
        segment.retries_used = retry_record.retries_used
        segment.failure_reason = final_reason
        self._fail_end_to_end(e2e, packet, final_reason)
        context = self._segment_contexts[mapping]
        reward_input = self._make_reward_input(
            context=context,
            segment=segment,
            packet=packet,
            retry_record=retry_record,
            settlement=SegmentSettlement.FAILURE,
            effective_hops=0,
            packet_delivered=False,
            failure_reason=final_reason,
        )
        self._settle_context(
            context,
            reward_input,
            terminal_reason="packet_dropped_after_retry_exhaustion",
        )
        start_node = int(e2e.route[segment.segment_start_index])
        self._finish_node_queue_service(start_node, mapping)

    def _receive_release(
        self,
        reservation: ReservationRecord,
        link_index: int,
        frame: PRMACFrame,
    ) -> None:
        """Settle reward before releasing the FIFO head to the next decision."""
        # Skip Day13's wrapper so settlement can occur before its queue release.
        super(FixedPRMACEndToEndController, self)._receive_release(
            reservation,
            link_index,
            frame,
        )
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

        retry_id = segment.retry_id
        if retry_id is None:
            raise RuntimeError("Completed RL segment must expose retry_id.")
        retry_record = self.retry_records[retry_id]
        context = self._segment_contexts[mapping]
        delivered = packet.status == PacketStatus.DELIVERED
        reward_input = self._make_reward_input(
            context=context,
            segment=segment,
            packet=packet,
            retry_record=retry_record,
            settlement=SegmentSettlement.SUCCESS,
            effective_hops=reservation.effective_hops,
            packet_delivered=delivered,
            failure_reason="",
        )
        terminal_reason = "packet_delivered" if delivered else None
        self._settle_context(context, reward_input, terminal_reason=terminal_reason)

        start_node = int(e2e.route[segment.segment_start_index])
        self._finish_node_queue_service(start_node, mapping)
        if e2e.status == EndToEndStatus.IN_PROGRESS:
            self._schedule_next_segment(e2e, packet)

    def _make_reward_input(
        self,
        *,
        context: SegmentRLContext,
        segment: EndToEndSegmentRecord,
        packet: Packet,
        retry_record: ReservationRetryRecord,
        settlement: SegmentSettlement,
        effective_hops: int,
        packet_delivered: bool,
        failure_reason: str,
    ) -> SegmentRewardInput:
        pr_nack_count = sum(
            attempt.status in {ReservationStatus.REJECTED, ReservationStatus.FAILED}
            for attempt in retry_record.attempts
        )
        control_bytes = self._segment_control_bytes(
            packet_id=int(packet.packet_id),
            segment_start_index=segment.segment_start_index,
            started_at=context.decision.selected_at,
            settled_at=self.now,
        )
        return SegmentRewardInput(
            decision=context.decision,
            packet_id=int(packet.packet_id),
            flow_id=context.flow_id,
            priority=int(packet.priority),
            queue_delay=segment.queue_delay,
            settled_at=self.now,
            settlement=settlement,
            effective_hops=effective_hops,
            retries_used=retry_record.retries_used,
            retry_limit=retry_record.retry_limit,
            pr_nack_count=int(pr_nack_count),
            control_bytes=control_bytes,
            payload_bytes=int(packet.size_bytes),
            packet_delivered=packet_delivered,
            failure_reason=failure_reason,
        )

    def _segment_control_bytes(
        self,
        *,
        packet_id: int,
        segment_start_index: int,
        started_at: float,
        settled_at: float,
    ) -> int:
        sizes = {
            PRMACFrameType.PR_REQ: self.config.pr_req_size_bytes,
            PRMACFrameType.PR_ACK: self.config.pr_ack_size_bytes,
            PRMACFrameType.PR_NACK: self.config.pr_nack_size_bytes,
            PRMACFrameType.RELEASE: self.config.release_size_bytes,
            PRMACFrameType.H_ACK: self.config.h_ack_size_bytes,
        }
        total = 0
        for frame in self.frames:
            if frame.packet_id != packet_id:
                continue
            if frame.segment_start_index != segment_start_index:
                continue
            if not started_at <= frame.created_at <= settled_at:
                continue
            total += sizes.get(frame.frame_type, 0)
        return int(total)

    def _settle_context(
        self,
        context: SegmentRLContext,
        reward_input: SegmentRewardInput,
        *,
        terminal_reason: str | None,
    ) -> None:
        agent = self.local_agent(context.node_id)
        reward, transition, update = agent.settle(
            reward_input,
            terminal_reason=terminal_reason,
        )
        succeeded = reward_input.settlement == SegmentSettlement.SUCCESS
        agent.record_local_outcome(
            succeeded=succeeded,
            retries_used=reward_input.retries_used,
        )
        context.reward_input = reward_input
        context.reward_breakdown = reward
        context.transition = transition
        context.update = update
        context.status = "TERMINAL_UPDATED" if update is not None else "SETTLED_PENDING"
        self.metrics.record_settlement(reward_input.settlement, reward)
        if update is not None:
            self.metrics.record_update(update)
        e2e = self.end_to_end_records[context.session_id]
        packet = self._session_packets[context.session_id]
        self._trace_e2e(
            "RL_SEGMENT_SETTLED",
            e2e,
            packet,
            segment_number=context.segment_index + 1,
            detail=(
                f"decision_id={context.decision.decision_id}, "
                f"settlement={reward_input.settlement.value}, "
                f"reward={reward.reward:.9f}, "
                f"terminal={update.terminal if update is not None else False}"
            ),
        )

    def _attach_update(
        self,
        transition: QTransition,
        update: QUpdateResult,
    ) -> None:
        context = self._contexts_by_decision_id.get(transition.decision_id)
        if context is None:
            raise RuntimeError("Q update cannot be linked to its segment decision.")
        context.transition = transition
        context.update = update
        context.status = (
            "TERMINAL_UPDATED" if update.terminal else "BOOTSTRAPPED_UPDATED"
        )
        self.metrics.record_update(update)

    def finalize_pending_learning(
        self,
        *,
        at: float | None = None,
        reason: str = "simulation_episode_end",
    ) -> list[QUpdateResult]:
        """Flush node-local pending experiences only at an explicit episode end."""
        terminal_at = self.now if at is None else float(at)
        if terminal_at < self.now:
            raise ValueError("Episode finalization cannot be scheduled in the past.")
        if not reason:
            raise ValueError("Episode finalization requires a reason.")
        updates: list[QUpdateResult] = []
        for node_id in sorted(self._agents):
            agent = self._agents[node_id]
            result = agent.finalize_pending(
                terminal_at=terminal_at,
                reason=reason,
            )
            if result is None:
                continue
            transition, update = result
            self._attach_update(transition, update)
            updates.append(update)
        return updates

    def rl_snapshot(self) -> dict[str, Any]:
        return {
            "protocol_integration_version": PROTOCOL_INTEGRATION_VERSION,
            "state_interface": "Day14 RLState unchanged",
            "action_interface": ACTION_DESIGN_VERSION,
            "reward_interface": REWARD_DESIGN_VERSION,
            "update_interface": UPDATE_DESIGN_VERSION,
            "decision_epoch": DECISION_EPOCH,
            "action_lifetime": ACTION_LIFETIME,
            "next_state_rule": LOCAL_NEXT_STATE_RULE,
            "distributed_agents": [
                self._agents[node_id].snapshot() for node_id in sorted(self._agents)
            ],
            "segment_contexts": [
                context.as_dict()
                for _, context in sorted(
                    self._segment_contexts.items(),
                    key=lambda item: (item[0][0], item[0][1]),
                )
            ],
            "pending_nodes": [
                node_id
                for node_id, agent in sorted(self._agents.items())
                if agent.has_pending_experience
            ],
        }

    def export_rl_summary_json(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config": asdict(self.config),
            "metrics": self.metrics.summary(self.table),
            "rl": self.rl_snapshot(),
            "end_to_end_sessions": self.end_to_end_snapshot(),
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
    "ACTION_LIFETIME",
    "BusyRatioProvider",
    "DECISION_EPOCH",
    "Day17RLPRMACConfig",
    "Day17RLPRMACMetrics",
    "LOCAL_NEXT_STATE_RULE",
    "LocalNodeAgent",
    "PROTOCOL_INTEGRATION_VERSION",
    "RLPRMACProtocolController",
    "SegmentRLContext",
]
