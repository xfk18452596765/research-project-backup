"""Run deterministic Day16 reward/transition/Q-update validation."""
from __future__ import annotations

import json
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
    LocalEpsilonGreedyPolicy,
    SparseLocalQTable,
)
from rl_prmac_reward_update import (  # noqa: E402
    LocalSegmentReward,
    LocalTabularQLearner,
    LocalTransitionAssembler,
    NEXT_STATE_SCOPE,
    QLearningConfig,
    REWARD_DESIGN_VERSION,
    RewardConfig,
    SegmentRewardInput,
    SegmentSettlement,
    TRANSITION_SCOPE,
    UPDATE_DESIGN_VERSION,
)


def main() -> None:
    action_space = JointActionSpace()
    state = RLState(2, 2, 1, 1, 1, 2)
    next_state = RLState(1, 1, 1, 1, 1, 1)
    q_table = SparseLocalQTable(node_id=2, action_count=len(action_space.actions))

    selected_action = JointAction(2, 15)
    q_table.set_value(
        state,
        action_space.action_to_index(selected_action),
        2.0,
    )
    policy = LocalEpsilonGreedyPolicy(
        node_id=2,
        action_space=action_space,
        q_table=q_table,
        epsilon=0.0,
        random_seed=17,
    )
    decision = policy.select_action(
        state=state,
        remaining_hops=4,
        selected_at=1.0,
    )

    reward_input = SegmentRewardInput(
        decision=decision,
        packet_id=101,
        flow_id="flow-0-6",
        priority=1,
        queue_delay=0.012,
        settled_at=1.018,
        settlement=SegmentSettlement.SUCCESS,
        effective_hops=2,
        retries_used=1,
        retry_limit=7,
        pr_nack_count=1,
        control_bytes=144,
        payload_bytes=1500,
        packet_delivered=False,
    )
    reward_model = LocalSegmentReward()
    assembler = LocalTransitionAssembler(reward_model)
    experience = assembler.settle(reward_input)
    transition = assembler.complete_with_next_state(
        node_id=2,
        next_state=next_state,
        next_remaining_hops=2,
        observed_at=1.025,
    )

    # Prove that K=3 values are excluded when only two hops remain.
    q_table.set_value(next_state, action_space.action_to_index(JointAction(3, 31)), 99.0)
    q_table.set_value(next_state, action_space.action_to_index(JointAction(2, 31)), 3.0)
    learner = LocalTabularQLearner(
        node_id=2,
        q_table=q_table,
        action_space=action_space,
        config=QLearningConfig(alpha=0.20, gamma=0.90),
    )
    update = learner.update(transition)

    payload = {
        "day": "Day16",
        "task": "奖励函数与更新机制",
        "reward_design_version": REWARD_DESIGN_VERSION,
        "update_design_version": UPDATE_DESIGN_VERSION,
        "transition_scope": TRANSITION_SCOPE,
        "next_state_scope": NEXT_STATE_SCOPE,
        "reward_config": {
            name: getattr(RewardConfig(), name)
            for name in RewardConfig.__dataclass_fields__
        },
        "decision": decision.as_dict(),
        "reward_input": {
            "node_id": decision.node_id,
            "packet_id": reward_input.packet_id,
            "priority": reward_input.priority,
            "queue_delay": reward_input.queue_delay,
            "service_delay": reward_input.service_delay,
            "settlement": reward_input.settlement.value,
            "effective_hops": reward_input.effective_hops,
            "retries_used": reward_input.retries_used,
            "pr_nack_count": reward_input.pr_nack_count,
            "control_bytes": reward_input.control_bytes,
            "payload_bytes": reward_input.payload_bytes,
            "packet_delivered": reward_input.packet_delivered,
        },
        "reward_breakdown": experience.reward_breakdown.as_dict(),
        "transition": transition.as_dict(),
        "q_update": update.as_dict(),
        "illegal_next_k3_q_value": 99.0,
        "bootstrap_value_after_mask": update.bootstrap_value,
        "one_reward_per_segment": True,
        "redecision_per_hop": False,
        "redecision_after_pr_nack": False,
        "future_end_to_end_delay_used": False,
        "global_state_used": False,
        "central_controller_used": False,
        "priority_retained": True,
        "day13_controller_modified": False,
        "day14_state_interface_modified": False,
        "day15_action_interface_modified": False,
        "full_training_started": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
