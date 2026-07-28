"""Run the final Day15 action-and-policy validation example."""
from __future__ import annotations

import json
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY14_CODE = DAILY_DIR / "Day14_Q-learning状态设计" / "code"
for path in (CURRENT_DIR, DAY14_CODE):
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(CURRENT_DIR), str(DAY14_CODE)]

from rl_prmac_state import RLState  # noqa: E402
from rl_prmac_action_policy import (  # noqa: E402
    ACTION_DESIGN_VERSION,
    JointAction,
    JointActionSpace,
    LocalEpsilonGreedyPolicy,
    SparseLocalQTable,
)


def main() -> None:
    state = RLState(2, 2, 2, 2, 1, 0)
    remaining_hops = 4
    action_space = JointActionSpace()
    q_table = SparseLocalQTable(node_id=2, action_count=len(action_space.actions))

    preferred = JointAction(3, 31)
    q_table.set_value(state, action_space.action_to_index(preferred), 5.0)
    policy = LocalEpsilonGreedyPolicy(
        node_id=2,
        action_space=action_space,
        q_table=q_table,
        epsilon=0.0,
        random_seed=17,
    )
    decision = policy.select_action(
        state=state,
        remaining_hops=remaining_hops,
        selected_at=1.0,
    )

    payload = {
        "day": "Day15",
        "task": "Q-learning动作与策略",
        "design_version": ACTION_DESIGN_VERSION,
        "decision_scope": "distributed_per_segment_start_node",
        "decision_time": "before_initial_difs_and_backoff",
        "action_scope": decision.action_scope,
        "action_space": [list(action.as_tuple()) for action in action_space.actions],
        "action_space_size": len(action_space.actions),
        "fixed_baseline_action": list(action_space.fixed_baseline_action.as_tuple()),
        "state_space_size": 1536,
        "state_action_upper_bound_per_node": action_space.dense_state_action_upper_bound,
        "legal_action_count_by_remaining_hops": {
            "1": len(action_space.valid_actions(1)),
            "2": len(action_space.valid_actions(2)),
            "3": len(action_space.valid_actions(3)),
            "6": len(action_space.valid_actions(6)),
        },
        "decision": decision.as_dict(),
        "retry_contention_windows": {
            "retry_0": decision.contention_window_for_retry(action_space, 0),
            "retry_1": decision.contention_window_for_retry(action_space, 1),
            "retry_2": decision.contention_window_for_retry(action_space, 2),
        },
        "illegal_k_is_masked_not_truncated": True,
        "redecision_on_each_pr_nack": False,
        "local_q_table_only": True,
        "fixed_baseline_controller_modified": False,
        "reward_implemented": False,
        "q_update_implemented": False,
        "training_started": False,
        "central_controller_used": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
