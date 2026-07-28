"""Day16 tests for local reward, transition assembly, and Q-learning update."""
from __future__ import annotations

import math
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY14_CODE = DAILY_DIR / "Day14_Q-learning状态设计" / "code"
DAY15_CODE = DAILY_DIR / "Day15_Q-learning动作与策略" / "code"
for path in (CURRENT_DIR, DAY15_CODE, DAY14_CODE):
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(CURRENT_DIR), str(DAY15_CODE), str(DAY14_CODE)]

from rl_prmac_state import RLState  # noqa: E402
from rl_prmac_action_policy import (  # noqa: E402
    JointAction,
    JointActionSpace,
    SegmentActionDecision,
    SelectionMode,
    SparseLocalQTable,
)
from rl_prmac_reward_update import (  # noqa: E402
    LocalSegmentReward,
    LocalTabularQLearner,
    LocalTransitionAssembler,
    NEXT_STATE_SCOPE,
    QLearningConfig,
    QTransition,
    REWARD_DESIGN_VERSION,
    RewardConfig,
    SegmentRewardInput,
    SegmentSettlement,
    TRANSITION_SCOPE,
    UPDATE_DESIGN_VERSION,
)

STATE_A = RLState(2, 1, 1, 0, 0, 1)
STATE_B = RLState(1, 2, 2, 2, 1, 2)
SPACE = JointActionSpace()


def make_decision(
    action: JointAction = JointAction(2, 15),
    *,
    node_id: int = 2,
    state: RLState = STATE_A,
    remaining_hops: int = 4,
    selected_at: float = 1.0,
    sequence: int = 1,
) -> SegmentActionDecision:
    index = SPACE.action_to_index(action)
    SPACE.validate_action(action, remaining_hops=remaining_hops)
    return SegmentActionDecision(
        decision_id=f"node-{node_id}:decision-{sequence}",
        node_id=node_id,
        state=state,
        remaining_hops=remaining_hops,
        action=action,
        action_index=index,
        selected_at=selected_at,
        selection_mode=SelectionMode.EXPLOIT,
        epsilon=0.0,
        legal_action_indices=SPACE.valid_action_indices(remaining_hops),
    )


def make_input(
    *,
    decision: SegmentActionDecision | None = None,
    priority: int = 0,
    queue_delay: float = 0.005,
    service_delay: float = 0.010,
    settlement: SegmentSettlement = SegmentSettlement.SUCCESS,
    effective_hops: int = 2,
    retries_used: int = 0,
    retry_limit: int = 7,
    pr_nack_count: int = 0,
    control_bytes: int = 96,
    payload_bytes: int = 1500,
    packet_delivered: bool = False,
    failure_reason: str = "",
) -> SegmentRewardInput:
    resolved = decision or make_decision()
    return SegmentRewardInput(
        decision=resolved,
        packet_id=101,
        flow_id="flow-0-6",
        priority=priority,
        queue_delay=queue_delay,
        settled_at=resolved.selected_at + service_delay,
        settlement=settlement,
        effective_hops=effective_hops,
        retries_used=retries_used,
        retry_limit=retry_limit,
        pr_nack_count=pr_nack_count,
        control_bytes=control_bytes,
        payload_bytes=payload_bytes,
        packet_delivered=packet_delivered,
        failure_reason=failure_reason,
    )


def make_transition(
    *,
    node_id: int = 2,
    state: RLState = STATE_A,
    action_index: int = 2,
    current_remaining_hops: int = 4,
    reward: float = 1.0,
    next_state: RLState | None = STATE_B,
    next_remaining_hops: int | None = 2,
    terminal: bool = False,
) -> QTransition:
    return QTransition(
        transition_id=f"node-{node_id}:transition-1",
        node_id=node_id,
        decision_id=f"node-{node_id}:decision-1",
        state=state,
        action_index=action_index,
        current_remaining_hops=current_remaining_hops,
        reward=reward,
        next_state=None if terminal else next_state,
        next_remaining_hops=None if terminal else next_remaining_hops,
        terminal=terminal,
        settled_at=1.01,
        next_observed_at=None if terminal else 1.02,
        terminal_reason="episode_end" if terminal else "",
    )


def test_design_versions_and_scopes_are_frozen() -> None:
    assert REWARD_DESIGN_VERSION == "Day16-Final-local-segment-reward-v1"
    assert UPDATE_DESIGN_VERSION == "Day16-Final-local-q-update-v1"
    assert TRANSITION_SCOPE == "one_complete_reservation_segment"
    assert NEXT_STATE_SCOPE == "same_node_next_local_decision_epoch"


def test_reward_input_exposes_no_future_end_to_end_delay_field() -> None:
    fields = SegmentRewardInput.__dataclass_fields__
    assert "end_to_end_delay" not in fields
    assert "future_delay" not in fields
    assert "global_state" not in fields


def test_successful_segment_has_positive_reward() -> None:
    result = LocalSegmentReward().calculate(make_input())
    assert result.reward > 0


def test_failed_segment_has_negative_reward() -> None:
    item = make_input(
        settlement=SegmentSettlement.FAILURE,
        effective_hops=0,
        retries_used=7,
        pr_nack_count=8,
        service_delay=0.080,
        failure_reason="retry_limit_exhausted",
    )
    assert LocalSegmentReward().calculate(item).reward < 0


def test_final_delivery_adds_local_terminal_delivery_bonus() -> None:
    decision = make_decision(JointAction(2, 15), remaining_hops=2)
    base = make_input(decision=decision, effective_hops=2)
    delivered = make_input(
        decision=decision,
        effective_hops=2,
        packet_delivered=True,
    )
    model = LocalSegmentReward()
    assert math.isclose(
        model.calculate(delivered).reward - model.calculate(base).reward,
        RewardConfig().delivery_bonus,
        abs_tol=1e-12,
    )


def test_longer_successful_progress_is_rewarded_without_forcing_k() -> None:
    short = make_input(
        decision=make_decision(JointAction(1, 15)),
        effective_hops=1,
    )
    long = make_input(
        decision=make_decision(JointAction(3, 15)),
        effective_hops=3,
    )
    model = LocalSegmentReward()
    assert model.calculate(long).reward > model.calculate(short).reward


def test_more_retries_reduce_reward() -> None:
    clean = make_input()
    retried = make_input(retries_used=4, pr_nack_count=4)
    model = LocalSegmentReward()
    assert model.calculate(retried).reward < model.calculate(clean).reward


def test_more_control_overhead_reduces_reward() -> None:
    low = make_input(control_bytes=48)
    high = make_input(control_bytes=1200)
    model = LocalSegmentReward()
    assert model.calculate(high).reward < model.calculate(low).reward


def test_longer_service_delay_reduces_reward() -> None:
    fast = make_input(service_delay=0.002)
    slow = make_input(service_delay=0.100)
    model = LocalSegmentReward()
    assert model.calculate(slow).reward < model.calculate(fast).reward


def test_longer_local_queue_delay_reduces_reward() -> None:
    short = make_input(queue_delay=0.001)
    long = make_input(queue_delay=0.200)
    model = LocalSegmentReward()
    assert model.calculate(long).reward < model.calculate(short).reward


def test_high_priority_delay_is_penalized_more_strongly() -> None:
    normal = make_input(priority=0, service_delay=0.025, queue_delay=0.050)
    urgent = make_input(priority=1, service_delay=0.025, queue_delay=0.050)
    model = LocalSegmentReward()
    assert model.calculate(urgent).reward < model.calculate(normal).reward


def test_priority_does_not_create_artificial_bonus_without_delay() -> None:
    normal = make_input(priority=0, service_delay=0.0, queue_delay=0.0)
    urgent = make_input(priority=1, service_delay=0.0, queue_delay=0.0)
    model = LocalSegmentReward()
    assert math.isclose(model.calculate(urgent).reward, model.calculate(normal).reward)


def test_reward_is_clipped_to_declared_bounds() -> None:
    model = LocalSegmentReward(
        config=RewardConfig(success_bonus=20.0, reward_min=-1.0, reward_max=1.0)
    )
    result = model.calculate(make_input())
    assert result.reward == 1.0
    assert result.unclipped_reward > result.reward


def test_failed_segment_cannot_claim_forwarded_hops() -> None:
    try:
        make_input(
            settlement=SegmentSettlement.FAILURE,
            effective_hops=1,
            failure_reason="retry_limit_exhausted",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Failed segments must not claim progress.")


def test_delivery_must_consume_all_locally_known_remaining_hops() -> None:
    decision = make_decision(JointAction(2, 15), remaining_hops=4)
    try:
        make_input(
            decision=decision,
            effective_hops=2,
            packet_delivered=True,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Premature final-delivery claims must fail.")


def test_normalized_components_stay_within_zero_and_one() -> None:
    result = LocalSegmentReward().calculate(
        make_input(
            queue_delay=99.0,
            service_delay=99.0,
            retries_used=7,
            pr_nack_count=8,
            control_bytes=10_000_000,
        )
    )
    values = (
        result.progress_normalized,
        result.service_delay_normalized,
        result.queue_delay_normalized,
        result.retry_pressure_normalized,
        result.control_overhead_normalized,
    )
    assert all(0.0 <= value <= 1.0 for value in values)


def test_transition_assembler_pairs_same_node_next_decision() -> None:
    assembler = LocalTransitionAssembler()
    experience = assembler.settle(make_input())
    assert assembler.has_pending(2)
    transition = assembler.complete_with_next_state(
        node_id=2,
        next_state=STATE_B,
        next_remaining_hops=2,
        observed_at=experience.settled_at + 0.001,
    )
    assert transition.node_id == 2
    assert transition.state == STATE_A
    assert transition.next_state == STATE_B
    assert transition.next_state_scope == NEXT_STATE_SCOPE
    assert not assembler.has_pending(2)


def test_transition_assembler_rejects_second_pending_segment_per_node() -> None:
    assembler = LocalTransitionAssembler()
    assembler.settle(make_input())
    try:
        assembler.settle(make_input())
    except RuntimeError:
        pass
    else:
        raise AssertionError("One local node cannot hold two unpaired experiences.")


def test_transition_assembler_rejects_unknown_node_completion() -> None:
    assembler = LocalTransitionAssembler()
    try:
        assembler.complete_with_next_state(
            node_id=9,
            next_state=STATE_B,
            next_remaining_hops=2,
            observed_at=2.0,
        )
    except KeyError:
        pass
    else:
        raise AssertionError("A missing local pending transition must fail.")


def test_terminal_transition_has_no_bootstrap_state() -> None:
    assembler = LocalTransitionAssembler()
    experience = assembler.settle(make_input())
    transition = assembler.finalize_terminal(
        node_id=2,
        terminal_at=experience.settled_at,
        reason="episode_end",
    )
    assert transition.terminal
    assert transition.next_state is None
    assert transition.next_remaining_hops is None


def test_nonterminal_transition_requires_next_state_and_hops() -> None:
    try:
        QTransition(
            transition_id="bad",
            node_id=2,
            decision_id="d",
            state=STATE_A,
            action_index=0,
            current_remaining_hops=1,
            reward=0.0,
            next_state=None,
            next_remaining_hops=None,
            terminal=False,
            settled_at=1.0,
            next_observed_at=None,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Non-terminal transitions require s'.")


def test_learning_parameter_boundaries_are_checked() -> None:
    invalid = [
        lambda: QLearningConfig(alpha=0.0),
        lambda: QLearningConfig(alpha=1.1),
        lambda: QLearningConfig(gamma=-0.1),
        lambda: QLearningConfig(gamma=1.1),
    ]
    for builder in invalid:
        try:
            builder()
        except ValueError:
            continue
        raise AssertionError("Invalid alpha/gamma must fail.")


def test_q_update_matches_bellman_formula() -> None:
    table = SparseLocalQTable(node_id=2, action_count=6)
    table.set_value(STATE_A, 2, 0.5)
    table.set_value(STATE_B, 0, 1.0)
    table.set_value(STATE_B, 2, 2.0)
    learner = LocalTabularQLearner(
        node_id=2,
        q_table=table,
        config=QLearningConfig(alpha=0.2, gamma=0.9),
    )
    result = learner.update(make_transition(reward=1.0))
    expected_target = 1.0 + 0.9 * 2.0
    expected_new = 0.5 + 0.2 * (expected_target - 0.5)
    assert math.isclose(result.target, expected_target, abs_tol=1e-12)
    assert math.isclose(result.new_q, expected_new, abs_tol=1e-12)
    assert math.isclose(table.get(STATE_A, 2), expected_new, abs_tol=1e-12)


def test_terminal_update_uses_zero_bootstrap() -> None:
    table = SparseLocalQTable(node_id=2, action_count=6)
    table.set_value(STATE_A, 2, 0.5)
    learner = LocalTabularQLearner(
        node_id=2,
        q_table=table,
        config=QLearningConfig(alpha=0.5, gamma=0.9),
    )
    result = learner.update(make_transition(reward=-1.0, terminal=True))
    assert result.bootstrap_value == 0.0
    assert result.target == -1.0
    assert math.isclose(result.new_q, -0.25, abs_tol=1e-12)


def test_illegal_next_action_is_excluded_from_max_q() -> None:
    table = SparseLocalQTable(node_id=2, action_count=6)
    table.set_value(STATE_B, 5, 99.0)  # K=3, illegal when next_remaining_hops=2
    table.set_value(STATE_B, 2, 3.0)   # K=2, legal
    learner = LocalTabularQLearner(
        node_id=2,
        q_table=table,
        config=QLearningConfig(alpha=1.0, gamma=1.0),
    )
    result = learner.update(make_transition(reward=0.0, next_remaining_hops=2))
    assert result.bootstrap_value == 3.0
    assert result.legal_next_action_indices == (0, 1, 2, 3)
    assert result.new_q == 3.0


def test_illegal_current_action_is_rejected_not_truncated() -> None:
    table = SparseLocalQTable(node_id=2, action_count=6)
    learner = LocalTabularQLearner(node_id=2, q_table=table)
    transition = make_transition(action_index=5, current_remaining_hops=2)
    try:
        learner.update(transition)
    except ValueError as exc:
        assert "not silently truncated" in str(exc)
    else:
        raise AssertionError("An illegal current K must fail.")


def test_learner_rejects_another_nodes_q_table() -> None:
    try:
        LocalTabularQLearner(
            node_id=2,
            q_table=SparseLocalQTable(node_id=4, action_count=6),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Cross-node Q-table ownership must fail.")


def test_learner_rejects_another_nodes_transition() -> None:
    learner = LocalTabularQLearner(
        node_id=2,
        q_table=SparseLocalQTable(node_id=2, action_count=6),
    )
    try:
        learner.update(make_transition(node_id=4))
    except ValueError:
        pass
    else:
        raise AssertionError("A node cannot update from another node's transition.")


def test_different_nodes_update_independent_q_tables() -> None:
    table_2 = SparseLocalQTable(node_id=2, action_count=6)
    table_4 = SparseLocalQTable(node_id=4, action_count=6)
    learner_2 = LocalTabularQLearner(
        node_id=2,
        q_table=table_2,
        config=QLearningConfig(alpha=1.0, gamma=0.0),
    )
    learner_4 = LocalTabularQLearner(
        node_id=4,
        q_table=table_4,
        config=QLearningConfig(alpha=1.0, gamma=0.0),
    )
    learner_2.update(make_transition(node_id=2, reward=1.0))
    learner_4.update(make_transition(node_id=4, reward=-1.0))
    assert table_2.get(STATE_A, 2) == 1.0
    assert table_4.get(STATE_A, 2) == -1.0


TESTS = [
    test_design_versions_and_scopes_are_frozen,
    test_reward_input_exposes_no_future_end_to_end_delay_field,
    test_successful_segment_has_positive_reward,
    test_failed_segment_has_negative_reward,
    test_final_delivery_adds_local_terminal_delivery_bonus,
    test_longer_successful_progress_is_rewarded_without_forcing_k,
    test_more_retries_reduce_reward,
    test_more_control_overhead_reduces_reward,
    test_longer_service_delay_reduces_reward,
    test_longer_local_queue_delay_reduces_reward,
    test_high_priority_delay_is_penalized_more_strongly,
    test_priority_does_not_create_artificial_bonus_without_delay,
    test_reward_is_clipped_to_declared_bounds,
    test_failed_segment_cannot_claim_forwarded_hops,
    test_delivery_must_consume_all_locally_known_remaining_hops,
    test_normalized_components_stay_within_zero_and_one,
    test_transition_assembler_pairs_same_node_next_decision,
    test_transition_assembler_rejects_second_pending_segment_per_node,
    test_transition_assembler_rejects_unknown_node_completion,
    test_terminal_transition_has_no_bootstrap_state,
    test_nonterminal_transition_requires_next_state_and_hops,
    test_learning_parameter_boundaries_are_checked,
    test_q_update_matches_bellman_formula,
    test_terminal_update_uses_zero_bootstrap,
    test_illegal_next_action_is_excluded_from_max_q,
    test_illegal_current_action_is_rejected_not_truncated,
    test_learner_rejects_another_nodes_q_table,
    test_learner_rejects_another_nodes_transition,
    test_different_nodes_update_independent_q_tables,
]


def main() -> None:
    for test in TESTS:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"\nAll Day16 reward/update tests passed. ({len(TESTS)} tests)")


if __name__ == "__main__":
    main()
