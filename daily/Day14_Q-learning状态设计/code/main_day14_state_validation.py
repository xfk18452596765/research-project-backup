"""Run the Day14 state-design validation example."""
from __future__ import annotations

import json
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from rl_prmac_state import LocalObservation, StateEncoder, enumerate_state_space_size


def main() -> None:
    observation = LocalObservation(
        node_id=2,
        packet_id=101,
        flow_id="alarm-flow-0-6",
        observed_at=0.100,
        remaining_hops=4,
        local_queue_length=4,
        queue_limit=200,
        priority=1,
        last_reservation_succeeded=False,
        recent_mean_retries=1.5,
        channel_busy_ratio=None,
    )
    state = StateEncoder().encode(observation)

    output = {
        "day": "Day14",
        "task": "Q-learning状态设计",
        "decision_scope": "distributed_per_segment_start_node",
        "raw_observation": {
            "node_id": observation.node_id,
            "packet_id": observation.packet_id,
            "flow_id": observation.flow_id,
            "remaining_hops": observation.remaining_hops,
            "local_queue_length": observation.local_queue_length,
            "queue_limit": observation.queue_limit,
            "priority": observation.priority,
            "last_reservation_succeeded": observation.last_reservation_succeeded,
            "recent_mean_retries": observation.recent_mean_retries,
            "channel_busy_ratio": observation.channel_busy_ratio,
        },
        "encoded_state": state.as_tuple(),
        "state_space_size": enumerate_state_space_size(),
        "local_observable_only": True,
        "unknown_channel_busy_is_explicit": state.channel_busy_bin == 0,
        "action_policy_implemented": False,
        "reward_update_implemented": False,
        "training_started": False,
        "central_controller_used": False,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
