"""Deterministic Day17 validation: Day14-Day16 interfaces inside Day13 lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
import sys

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
paths = (
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
)
for path in paths:
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(path) for path in paths if path.exists()]

from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from rl_prmac_state import LocalObservation, StateEncoder  # noqa: E402
from rl_prmac_action_policy import JointAction  # noqa: E402
from rl_prmac_protocol_controller import (  # noqa: E402
    ACTION_LIFETIME,
    DECISION_EPOCH,
    LOCAL_NEXT_STATE_RULE,
    PROTOCOL_INTEGRATION_VERSION,
    Day17RLPRMACConfig,
    RLPRMACProtocolController,
)


def chain_adjacency(hops: int) -> dict[int, set[int]]:
    return {
        node: {
            neighbor
            for neighbor in (node - 1, node + 1)
            if 0 <= neighbor <= hops
        }
        for node in range(hops + 1)
    }


def encode_initial_state(
    *,
    node_id: int,
    packet_id: int,
    flow_id: str,
    remaining_hops: int,
    priority: int,
    busy_ratio: float | None,
) -> object:
    return StateEncoder().encode(
        LocalObservation(
            node_id=node_id,
            packet_id=packet_id,
            flow_id=flow_id,
            observed_at=0.0,
            remaining_hops=remaining_hops,
            local_queue_length=1,
            queue_limit=200,
            priority=priority,
            last_reservation_succeeded=None,
            recent_mean_retries=0.0,
            channel_busy_ratio=busy_ratio,
        )
    )


def main() -> None:
    hops = 5
    packet_id = 17_001
    flow_id = "day17-main-validation"
    priority = 1
    busy_by_node = {0: 0.20, 3: 0.70}

    simulator = Simulator()
    simulator.log_enabled = False
    controller = RLPRMACProtocolController(
        simulator=simulator,
        config=Day17RLPRMACConfig(epsilon=0.0, random_seed=17),
        adjacency=chain_adjacency(hops),
        busy_ratio_provider=lambda node_id, now: busy_by_node.get(node_id),
    )

    preferred = {
        0: (encode_initial_state(
            node_id=0,
            packet_id=packet_id,
            flow_id=flow_id,
            remaining_hops=5,
            priority=priority,
            busy_ratio=0.20,
        ), JointAction(3, 31)),
        3: (encode_initial_state(
            node_id=3,
            packet_id=packet_id,
            flow_id=flow_id,
            remaining_hops=2,
            priority=priority,
            busy_ratio=0.70,
        ), JointAction(2, 15)),
    }
    for node_id, (state, action) in preferred.items():
        agent = controller.local_agent(node_id)
        action_index = controller.action_space.action_to_index(action)
        agent.q_table.set_value(state, action_index, 5.0)

    packet = Packet(
        packet_id,
        0,
        hops,
        0.0,
        priority=priority,
        route=tuple(range(hops + 1)),
    )
    session_id = controller.schedule_end_to_end(packet, flow_id=flow_id)
    simulator.run()
    episode_flush_updates = controller.finalize_pending_learning(
        reason="day17_main_validation_episode_end"
    )

    record = controller.end_to_end_records[session_id]
    contexts = [
        controller.segment_context(session_id, index)
        for index in range(len(record.segments))
    ]
    metrics = controller.metrics.summary(controller.table)
    payload = {
        "day": "Day17",
        "task": "RL-PRMAC协议集成",
        "protocol_integration_version": PROTOCOL_INTEGRATION_VERSION,
        "decision_epoch": DECISION_EPOCH,
        "action_lifetime": ACTION_LIFETIME,
        "next_state_rule": LOCAL_NEXT_STATE_RULE,
        "distributed_design": {
            "node_local_observation_only": True,
            "independent_q_table_per_node": True,
            "central_controller_used": False,
            "global_network_state_used": False,
            "per_hop_redecision": False,
            "redecision_after_pr_nack": False,
        },
        "frozen_interfaces": {
            "day14_state_unchanged": True,
            "day15_action_catalog": [
                list(action.as_tuple()) for action in controller.action_space.actions
            ],
            "day16_reward_unchanged": True,
            "day16_q_update_unchanged": True,
        },
        "session": {
            "session_id": session_id,
            "status": record.status.value,
            "packet_status": packet.status.value,
            "delivered": packet.status == PacketStatus.DELIVERED,
            "route": list(packet.route),
            "segment_count": len(record.segments),
            "selected_actions": [
                list(context.decision.action.as_tuple()) for context in contexts
            ],
            "effective_hops": [
                segment.effective_hops for segment in record.segments
            ],
            "segment_access_cw": [
                segment.access_cw for segment in record.segments
            ],
            "segment_rewards": [
                context.reward_breakdown.reward for context in contexts
            ],
            "segment_update_terminal": [
                context.update.terminal for context in contexts
            ],
        },
        "learning": {
            "q_updates": metrics["q_updates"],
            "terminal_q_updates": metrics["terminal_q_updates"],
            "bootstrapped_q_updates": metrics["bootstrapped_q_updates"],
            "episode_flush_update_count": len(episode_flush_updates),
            "pending_nodes_after_flush": controller.rl_snapshot()["pending_nodes"],
            "complete_training_started": False,
            "hyperparameter_search_started": False,
        },
        "metrics": metrics,
        "rl_snapshot": controller.rl_snapshot(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
