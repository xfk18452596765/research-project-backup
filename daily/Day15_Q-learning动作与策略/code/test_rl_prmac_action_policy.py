"""Day15 tests for the frozen joint action space and local policy."""
from __future__ import annotations

import math
from pathlib import Path
import random
import sys

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY14_CODE = DAILY_DIR / "Day14_Q-learning状态设计" / "code"

for path in (CURRENT_DIR, DAY14_CODE):
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(CURRENT_DIR), str(DAY14_CODE)]

from rl_prmac_state import RLState, enumerate_state_space_size  # noqa: E402
from rl_prmac_action_policy import (  # noqa: E402
    ACTION_DESIGN_VERSION,
    FIXED_BASELINE_ACTION,
    JointAction,
    JointActionSpace,
    LocalEpsilonGreedyPolicy,
    SelectionMode,
    SparseLocalQTable,
)

STATE = RLState(2, 2, 2, 2, 1, 0)


def test_design_version_is_frozen() -> None:
    assert ACTION_DESIGN_VERSION == "Day15-Final-action-policy-v1"


def test_default_action_order_matches_original_six_action_design() -> None:
    space = JointActionSpace()
    assert [action.as_tuple() for action in space.actions] == [
        (1, 15),
        (1, 31),
        (2, 15),
        (2, 31),
        (3, 15),
        (3, 31),
    ]


def test_fixed_baseline_action_is_preserved() -> None:
    space = JointActionSpace()
    assert FIXED_BASELINE_ACTION == JointAction(2, 15)
    assert space.fixed_baseline_action in space.actions
    assert space.action_to_index(space.fixed_baseline_action) == 2


def test_state_action_upper_bound_is_9216_per_node() -> None:
    space = JointActionSpace()
    assert enumerate_state_space_size() == 1536
    assert len(space.actions) == 6
    assert space.dense_state_action_upper_bound == 9216


def test_action_index_round_trip_is_stable() -> None:
    space = JointActionSpace()
    for index, action in enumerate(space.actions):
        assert space.action_to_index(action) == index
        assert space.index_to_action(index) == action


def test_legal_mask_counts_follow_remaining_hops() -> None:
    space = JointActionSpace()
    assert sum(space.legal_mask(1)) == 2
    assert sum(space.legal_mask(2)) == 4
    assert sum(space.legal_mask(3)) == 6
    assert sum(space.legal_mask(8)) == 6


def test_illegal_k_is_rejected_instead_of_truncated() -> None:
    space = JointActionSpace()
    illegal = JointAction(3, 15)
    try:
        space.validate_action(illegal, remaining_hops=2)
    except ValueError as exc:
        assert "not silently truncated" in str(exc)
    else:
        raise AssertionError("K > remaining_hops must be rejected.")


def test_invalid_action_space_parameters_are_rejected() -> None:
    invalid_builders = [
        lambda: JointActionSpace(k_values=(1, 1, 2)),
        lambda: JointActionSpace(cw_values=(15, 16, 31)),
        lambda: JointActionSpace(k_values=(1, 3), cw_values=(15, 31)),
        lambda: JointActionSpace(cw_max=15),
    ]
    for builder in invalid_builders:
        try:
            builder()
        except ValueError:
            continue
        raise AssertionError("Invalid action-space configuration must fail.")


def test_beb_starts_from_action_selected_initial_cw_and_caps() -> None:
    space = JointActionSpace()
    small = JointAction(2, 15)
    large = JointAction(2, 31)
    assert [space.contention_window_for_retry(small, n) for n in range(4)] == [
        15, 31, 63, 127
    ]
    assert [space.contention_window_for_retry(large, n) for n in range(3)] == [
        31, 63, 127
    ]
    assert space.contention_window_for_retry(large, 10) == 1023


def test_backoff_sampling_is_reproducible_and_bounded() -> None:
    space = JointActionSpace()
    action = JointAction(3, 31)
    rng_a = random.Random(27)
    rng_b = random.Random(27)
    samples_a = [
        space.sample_backoff_slots(action, retry_number=1, rng=rng_a)
        for _ in range(20)
    ]
    samples_b = [
        space.sample_backoff_slots(action, retry_number=1, rng=rng_b)
        for _ in range(20)
    ]
    assert samples_a == samples_b
    assert all(0 <= value <= 63 for value in samples_a)


def test_access_delay_matches_existing_slot_and_difs_defaults() -> None:
    space = JointActionSpace()
    assert math.isclose(space.access_delay(20), 50e-6 + 20 * 20e-6, abs_tol=1e-15)


def test_sparse_q_table_defaults_to_zero() -> None:
    space = JointActionSpace()
    table = SparseLocalQTable(node_id=2, action_count=len(space.actions))
    assert table.entry_count == 0
    assert table.values_for(STATE) == (0.0,) * 6


def test_sparse_q_table_rejects_invalid_values_and_indices() -> None:
    table = SparseLocalQTable(node_id=2, action_count=6)
    invalid_calls = [
        lambda: table.get(STATE, -1),
        lambda: table.get(STATE, 6),
        lambda: table.set_value(STATE, 0, float("nan")),
        lambda: table.set_value(STATE, 0, float("inf")),
    ]
    for call in invalid_calls:
        try:
            call()
        except (IndexError, ValueError):
            continue
        raise AssertionError("Invalid Q-table access must fail.")


def test_greedy_policy_selects_highest_legal_q_value() -> None:
    space = JointActionSpace()
    table = SparseLocalQTable(node_id=2, action_count=6)
    best = JointAction(3, 31)
    table.set_value(STATE, space.action_to_index(best), 5.0)
    policy = LocalEpsilonGreedyPolicy(
        node_id=2,
        action_space=space,
        q_table=table,
        epsilon=0.0,
        random_seed=17,
    )
    decision = policy.select_action(state=STATE, remaining_hops=4, selected_at=1.0)
    assert decision.action == best
    assert decision.selection_mode == SelectionMode.EXPLOIT


def test_illegal_high_q_action_is_masked() -> None:
    space = JointActionSpace()
    table = SparseLocalQTable(node_id=2, action_count=6)
    illegal = JointAction(3, 31)
    legal = JointAction(2, 15)
    table.set_value(STATE, space.action_to_index(illegal), 99.0)
    table.set_value(STATE, space.action_to_index(legal), 3.0)
    policy = LocalEpsilonGreedyPolicy(
        node_id=2,
        action_space=space,
        q_table=table,
        epsilon=0.0,
        random_seed=7,
    )
    decision = policy.select_action(state=STATE, remaining_hops=2)
    assert decision.action == legal
    assert decision.action.reservation_length_k <= 2


def test_exploration_never_selects_an_illegal_action() -> None:
    policy = LocalEpsilonGreedyPolicy(node_id=2, epsilon=1.0, random_seed=11)
    decisions = [
        policy.select_action(state=STATE, remaining_hops=1)
        for _ in range(50)
    ]
    assert all(decision.action.reservation_length_k == 1 for decision in decisions)
    assert all(decision.selection_mode == SelectionMode.EXPLORE for decision in decisions)


def test_exploration_is_reproducible_with_same_seed() -> None:
    kwargs = {"node_id": 2, "epsilon": 1.0, "random_seed": 27}
    policy_a = LocalEpsilonGreedyPolicy(**kwargs)
    policy_b = LocalEpsilonGreedyPolicy(**kwargs)
    seq_a = [
        policy_a.select_action(state=STATE, remaining_hops=3).action
        for _ in range(12)
    ]
    seq_b = [
        policy_b.select_action(state=STATE, remaining_hops=3).action
        for _ in range(12)
    ]
    assert seq_a == seq_b


def test_equal_q_tie_breaking_is_reproducible() -> None:
    kwargs = {"node_id": 2, "epsilon": 0.0, "random_seed": 37}
    policy_a = LocalEpsilonGreedyPolicy(**kwargs)
    policy_b = LocalEpsilonGreedyPolicy(**kwargs)
    seq_a = [
        policy_a.select_action(state=STATE, remaining_hops=3).action
        for _ in range(12)
    ]
    seq_b = [
        policy_b.select_action(state=STATE, remaining_hops=3).action
        for _ in range(12)
    ]
    assert seq_a == seq_b


def test_different_nodes_keep_independent_local_q_tables() -> None:
    space = JointActionSpace()
    table_2 = SparseLocalQTable(node_id=2, action_count=6)
    table_4 = SparseLocalQTable(node_id=4, action_count=6)
    action_2 = JointAction(3, 31)
    action_4 = JointAction(1, 15)
    table_2.set_value(STATE, space.action_to_index(action_2), 5.0)
    table_4.set_value(STATE, space.action_to_index(action_4), 5.0)
    policy_2 = LocalEpsilonGreedyPolicy(
        node_id=2, action_space=space, q_table=table_2, epsilon=0.0, random_seed=7
    )
    policy_4 = LocalEpsilonGreedyPolicy(
        node_id=4, action_space=space, q_table=table_4, epsilon=0.0, random_seed=7
    )
    assert policy_2.select_action(state=STATE, remaining_hops=3).action == action_2
    assert policy_4.select_action(state=STATE, remaining_hops=3).action == action_4


def test_policy_rejects_another_nodes_q_table() -> None:
    try:
        LocalEpsilonGreedyPolicy(
            node_id=2,
            q_table=SparseLocalQTable(node_id=4, action_count=6),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Cross-node Q-table use must be rejected.")


def test_decision_holds_one_action_across_the_retry_sequence() -> None:
    space = JointActionSpace()
    table = SparseLocalQTable(node_id=2, action_count=6)
    selected = JointAction(2, 31)
    table.set_value(STATE, space.action_to_index(selected), 4.0)
    policy = LocalEpsilonGreedyPolicy(
        node_id=2,
        action_space=space,
        q_table=table,
        epsilon=0.0,
        random_seed=5,
    )
    decision = policy.select_action(state=STATE, remaining_hops=4)
    assert decision.action_scope == "one_segment_retry_sequence"
    assert decision.action == selected
    assert [decision.contention_window_for_retry(space, n) for n in range(3)] == [
        31, 63, 127
    ]


def test_decision_serialization_is_auditable() -> None:
    policy = LocalEpsilonGreedyPolicy(node_id=2, epsilon=0.0, random_seed=7)
    decision = policy.select_action(state=STATE, remaining_hops=2, selected_at=1.25)
    payload = decision.as_dict()
    assert payload["decision_id"] == "node-2:decision-1"
    assert payload["node_id"] == 2
    assert payload["state"] == [2, 2, 2, 2, 1, 0]
    assert payload["remaining_hops"] == 2
    assert payload["action_index"] in payload["legal_action_indices"]
    assert payload["action_scope"] == "one_segment_retry_sequence"


def test_day15_exposes_no_reward_update_or_training_api() -> None:
    table = SparseLocalQTable(node_id=2, action_count=6)
    policy = LocalEpsilonGreedyPolicy(node_id=2)
    forbidden = (
        "reward",
        "calculate_reward",
        "bellman_update",
        "update_from_transition",
        "train",
        "fit",
    )
    assert all(not hasattr(table, name) for name in forbidden)
    assert all(not hasattr(policy, name) for name in forbidden)


TESTS = [
    test_design_version_is_frozen,
    test_default_action_order_matches_original_six_action_design,
    test_fixed_baseline_action_is_preserved,
    test_state_action_upper_bound_is_9216_per_node,
    test_action_index_round_trip_is_stable,
    test_legal_mask_counts_follow_remaining_hops,
    test_illegal_k_is_rejected_instead_of_truncated,
    test_invalid_action_space_parameters_are_rejected,
    test_beb_starts_from_action_selected_initial_cw_and_caps,
    test_backoff_sampling_is_reproducible_and_bounded,
    test_access_delay_matches_existing_slot_and_difs_defaults,
    test_sparse_q_table_defaults_to_zero,
    test_sparse_q_table_rejects_invalid_values_and_indices,
    test_greedy_policy_selects_highest_legal_q_value,
    test_illegal_high_q_action_is_masked,
    test_exploration_never_selects_an_illegal_action,
    test_exploration_is_reproducible_with_same_seed,
    test_equal_q_tie_breaking_is_reproducible,
    test_different_nodes_keep_independent_local_q_tables,
    test_policy_rejects_another_nodes_q_table,
    test_decision_holds_one_action_across_the_retry_sequence,
    test_decision_serialization_is_auditable,
    test_day15_exposes_no_reward_update_or_training_api,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"[PASS] {test.__name__}")
    print()
    print("All Day15 Q-learning action-and-policy tests passed.")
