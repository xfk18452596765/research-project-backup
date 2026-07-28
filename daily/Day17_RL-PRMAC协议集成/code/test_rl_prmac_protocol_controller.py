"""Focused Day17 tests for distributed RL-PRMAC controller integration."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile

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
for path in (
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
):
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [
    str(path)
    for path in (
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
    if path.exists()
]

from fixed_prmac_end_to_end import EndToEndStatus  # type: ignore  # noqa: E402
from fixed_prmac_messages import ReservationStatus  # type: ignore  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from rl_prmac_state import LocalObservation, RLState, StateEncoder  # noqa: E402
from rl_prmac_action_policy import (  # noqa: E402
    ACTION_DESIGN_VERSION,
    JointAction,
)
from rl_prmac_reward_update import (  # noqa: E402
    REWARD_DESIGN_VERSION,
    UPDATE_DESIGN_VERSION,
)
from rl_prmac_protocol_controller import (  # noqa: E402
    ACTION_LIFETIME,
    DECISION_EPOCH,
    LOCAL_NEXT_STATE_RULE,
    PROTOCOL_INTEGRATION_VERSION,
    Day17RLPRMACConfig,
    RLPRMACProtocolController,
)


def chain_adjacency(hops: int) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {}
    for node in range(hops + 1):
        neighbors: set[int] = set()
        if node > 0:
            neighbors.add(node - 1)
        if node < hops:
            neighbors.add(node + 1)
        adjacency[node] = neighbors
    return adjacency


def make_controller(
    hops: int,
    *,
    config: Day17RLPRMACConfig | None = None,
    busy_ratio_provider=None,
) -> tuple[Simulator, RLPRMACProtocolController]:
    simulator = Simulator()
    simulator.log_enabled = False
    controller = RLPRMACProtocolController(
        simulator=simulator,
        config=config or Day17RLPRMACConfig(epsilon=0.0, random_seed=7),
        adjacency=chain_adjacency(hops),
        busy_ratio_provider=busy_ratio_provider,
    )
    return simulator, controller


def first_state(
    *,
    node_id: int,
    packet_id: int,
    flow_id: str,
    remaining_hops: int,
    queue_length: int = 1,
    queue_limit: int = 200,
    priority: int = 0,
    last_succeeded: bool | None = None,
    recent_mean_retries: float = 0.0,
    busy_ratio: float | None = None,
) -> RLState:
    return StateEncoder().encode(
        LocalObservation(
            node_id=node_id,
            packet_id=packet_id,
            flow_id=flow_id,
            observed_at=0.0,
            remaining_hops=remaining_hops,
            local_queue_length=queue_length,
            queue_limit=queue_limit,
            priority=priority,
            last_reservation_succeeded=last_succeeded,
            recent_mean_retries=recent_mean_retries,
            channel_busy_ratio=busy_ratio,
        )
    )


def prefer_action(
    controller: RLPRMACProtocolController,
    *,
    node_id: int,
    state: RLState,
    action: JointAction,
    value: float = 10.0,
) -> None:
    agent = controller.local_agent(node_id)
    index = controller.action_space.action_to_index(action)
    agent.q_table.set_value(state, index, value)


def run_single(
    hops: int,
    *,
    packet_id: int,
    action: JointAction,
    priority: int = 0,
    busy_ratio_provider=None,
) -> tuple[Simulator, RLPRMACProtocolController, Packet, str]:
    simulator, controller = make_controller(
        hops,
        busy_ratio_provider=busy_ratio_provider,
    )
    flow_id = f"day17-single-{hops}"
    state = first_state(
        node_id=0,
        packet_id=packet_id,
        flow_id=flow_id,
        remaining_hops=hops,
        priority=priority,
        busy_ratio=(
            None if busy_ratio_provider is None else busy_ratio_provider(0, 0.0)
        ),
    )
    prefer_action(controller, node_id=0, state=state, action=action)
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
    return simulator, controller, packet, session_id


def test_frozen_versions_and_scopes() -> None:
    assert PROTOCOL_INTEGRATION_VERSION == "Day17-Final-distributed-controller-integration-v1"
    assert DECISION_EPOCH == "local_fifo_head_before_initial_difs_and_backoff"
    assert ACTION_LIFETIME == "one_complete_segment_retry_sequence"
    assert LOCAL_NEXT_STATE_RULE == "same_node_next_local_decision_epoch"
    assert ACTION_DESIGN_VERSION == "Day15-Final-action-policy-v1"
    assert REWARD_DESIGN_VERSION == "Day16-Final-local-segment-reward-v1"
    assert UPDATE_DESIGN_VERSION == "Day16-Final-local-q-update-v1"


def test_default_action_catalog_is_unchanged() -> None:
    _, controller = make_controller(3)
    assert [action.as_tuple() for action in controller.action_space.actions] == [
        (1, 15),
        (1, 31),
        (2, 15),
        (2, 31),
        (3, 15),
        (3, 31),
    ]


def test_each_node_owns_an_independent_q_table_and_policy() -> None:
    _, controller = make_controller(4)
    agent0 = controller.local_agent(0)
    agent2 = controller.local_agent(2)
    assert agent0 is not agent2
    assert agent0.q_table is not agent2.q_table
    assert agent0.policy is not agent2.policy
    assert agent0.learner is not agent2.learner
    state = RLState(2, 0, 0, 0, 0, 0)
    agent0.q_table.set_value(state, 0, 5.0)
    assert agent2.q_table.get(state, 0) == 0.0


def test_decision_is_made_before_initial_access_and_applies_selected_cw() -> None:
    _, controller, _, session_id = run_single(
        3,
        packet_id=1700,
        action=JointAction(3, 31),
    )
    record = controller.end_to_end_records[session_id]
    segment = record.segments[0]
    context = controller.segment_context(session_id, 0)
    assert context.decision.selected_at == segment.queue_service_started_at
    assert segment.access_cw == 31
    assert segment.access_completed_at is not None
    assert context.decision.selected_at < segment.access_completed_at
    events = [item.event for item in controller.end_to_end_trace]
    assert events.index("RL_SEGMENT_DECISION") < events.index("SEGMENT_ACCESS_BACKOFF")


def test_selected_k_is_applied_exactly_without_silent_truncation() -> None:
    _, controller, packet, session_id = run_single(
        3,
        packet_id=1701,
        action=JointAction(3, 15),
    )
    segment = controller.end_to_end_records[session_id].segments[0]
    reservation = controller.table.get(segment.reservation_id)
    assert packet.status == PacketStatus.DELIVERED
    assert segment.effective_hops == 3
    assert reservation.requested_hops == 3
    assert reservation.effective_hops == 3


def test_illegal_large_k_is_masked_at_one_remaining_hop() -> None:
    simulator, controller = make_controller(1)
    flow_id = "day17-mask"
    state = first_state(
        node_id=0,
        packet_id=1702,
        flow_id=flow_id,
        remaining_hops=1,
    )
    agent = controller.local_agent(0)
    illegal_index = controller.action_space.action_to_index(JointAction(3, 31))
    agent.q_table.set_value(state, illegal_index, 99.0)
    packet = Packet(1702, 0, 1, 0.0, route=(0, 1))
    session_id = controller.schedule_end_to_end(packet, flow_id=flow_id)
    simulator.run()
    decision = controller.segment_context(session_id, 0).decision
    assert decision.action.reservation_length_k == 1
    assert decision.action_index in controller.action_space.valid_action_indices(1)


def test_default_channel_busy_state_remains_unknown_not_low() -> None:
    _, controller, _, session_id = run_single(
        2,
        packet_id=1703,
        action=JointAction(2, 15),
    )
    context = controller.segment_context(session_id, 0)
    assert context.observation.channel_busy_ratio is None
    assert context.state.channel_busy_bin == 0


def test_local_busy_provider_is_encoded_without_global_state() -> None:
    provider = lambda node_id, now: 0.75 if node_id == 0 else None
    _, controller, _, session_id = run_single(
        2,
        packet_id=1704,
        action=JointAction(2, 15),
        busy_ratio_provider=provider,
    )
    context = controller.segment_context(session_id, 0)
    assert context.observation.channel_busy_ratio == 0.75
    assert context.state.channel_busy_bin == 3
    fields = set(context.observation.__dataclass_fields__)
    assert "global_state" not in fields
    assert "future_end_to_end_delay" not in fields


def test_success_reward_is_settled_only_after_release() -> None:
    _, controller, packet, session_id = run_single(
        2,
        packet_id=1705,
        action=JointAction(2, 15),
    )
    segment = controller.end_to_end_records[session_id].segments[0]
    context = controller.segment_context(session_id, 0)
    assert packet.status == PacketStatus.DELIVERED
    assert segment.forwarding_completed_at is not None
    assert segment.released_at is not None
    assert context.reward_input is not None
    assert math.isclose(context.reward_input.settled_at, segment.released_at, abs_tol=1e-15)
    assert segment.released_at >= segment.forwarding_completed_at
    assert context.reward_breakdown is not None
    assert context.reward_breakdown.reward > 0.0


def test_final_delivery_creates_immediate_terminal_update() -> None:
    _, controller, _, session_id = run_single(
        2,
        packet_id=1706,
        action=JointAction(2, 15),
    )
    context = controller.segment_context(session_id, 0)
    assert context.status == "TERMINAL_UPDATED"
    assert context.transition is not None and context.transition.terminal
    assert context.update is not None and context.update.terminal
    assert context.update.bootstrap_value == 0.0
    assert context.update.legal_next_action_indices == ()


def test_nonfinal_segment_waits_for_same_node_next_decision() -> None:
    simulator, controller = make_controller(4)
    flow_id = "day17-one-packet"
    state0 = first_state(
        node_id=0,
        packet_id=1707,
        flow_id=flow_id,
        remaining_hops=4,
    )
    state2 = first_state(
        node_id=2,
        packet_id=1707,
        flow_id=flow_id,
        remaining_hops=2,
    )
    prefer_action(controller, node_id=0, state=state0, action=JointAction(2, 15))
    prefer_action(controller, node_id=2, state=state2, action=JointAction(2, 15))
    packet = Packet(1707, 0, 4, 0.0, route=(0, 1, 2, 3, 4))
    session_id = controller.schedule_end_to_end(packet, flow_id=flow_id)
    simulator.run()
    first = controller.segment_context(session_id, 0)
    second = controller.segment_context(session_id, 1)
    assert first.status == "SETTLED_PENDING"
    assert first.transition is None and first.update is None
    assert controller.local_agent(0).has_pending_experience
    assert second.status == "TERMINAL_UPDATED"


def test_another_nodes_decision_never_bootstraps_the_first_nodes_q_table() -> None:
    simulator, controller = make_controller(4)
    flow_id = "day17-node-isolation"
    prefer_action(
        controller,
        node_id=0,
        state=first_state(node_id=0, packet_id=1708, flow_id=flow_id, remaining_hops=4),
        action=JointAction(2, 15),
    )
    prefer_action(
        controller,
        node_id=2,
        state=first_state(node_id=2, packet_id=1708, flow_id=flow_id, remaining_hops=2),
        action=JointAction(2, 15),
    )
    packet = Packet(1708, 0, 4, 0.0, route=(0, 1, 2, 3, 4))
    session_id = controller.schedule_end_to_end(packet, flow_id=flow_id)
    simulator.run()
    assert controller.segment_context(session_id, 0).update is None
    assert controller.local_agent(0).q_table.entry_count == 1  # preloaded only
    assert controller.local_agent(2).updates[-1].terminal


def test_same_node_next_fifo_head_completes_bootstrapped_update() -> None:
    simulator, controller = make_controller(4)
    flow_id = "day17-two-packets"
    # The first decision starts immediately; the second packet then waits behind it.
    prefer_action(
        controller,
        node_id=0,
        state=first_state(
            node_id=0,
            packet_id=1710,
            flow_id=flow_id,
            remaining_hops=4,
            queue_length=1,
        ),
        action=JointAction(2, 15),
    )
    prefer_action(
        controller,
        node_id=0,
        state=first_state(
            node_id=0,
            packet_id=1711,
            flow_id=flow_id,
            remaining_hops=4,
            queue_length=1,
            last_succeeded=True,
        ),
        action=JointAction(2, 15),
    )
    for node_id in (2,):
        for packet_id in (1710, 1711):
            prefer_action(
                controller,
                node_id=node_id,
                state=first_state(
                    node_id=node_id,
                    packet_id=packet_id,
                    flow_id=flow_id,
                    remaining_hops=2,
                ),
                action=JointAction(2, 15),
            )
    p1 = Packet(1710, 0, 4, 0.0, route=(0, 1, 2, 3, 4))
    p2 = Packet(1711, 0, 4, 0.0, route=(0, 1, 2, 3, 4))
    sid1 = controller.schedule_end_to_end(p1, flow_id=flow_id, at=0.0)
    controller.schedule_end_to_end(p2, flow_id=flow_id, at=0.0)
    simulator.run()
    first = controller.segment_context(sid1, 0)
    assert first.status == "BOOTSTRAPPED_UPDATED"
    assert first.transition is not None and not first.transition.terminal
    assert first.transition.node_id == 0
    assert first.update is not None and not first.update.terminal
    assert first.update.legal_next_action_indices == (0, 1, 2, 3, 4, 5)


def test_explicit_episode_end_flushes_only_remaining_local_pending_items() -> None:
    simulator, controller = make_controller(4)
    flow_id = "day17-flush"
    prefer_action(
        controller,
        node_id=0,
        state=first_state(node_id=0, packet_id=1712, flow_id=flow_id, remaining_hops=4),
        action=JointAction(2, 15),
    )
    prefer_action(
        controller,
        node_id=2,
        state=first_state(node_id=2, packet_id=1712, flow_id=flow_id, remaining_hops=2),
        action=JointAction(2, 15),
    )
    packet = Packet(1712, 0, 4, 0.0, route=(0, 1, 2, 3, 4))
    session_id = controller.schedule_end_to_end(packet, flow_id=flow_id)
    simulator.run()
    assert controller.rl_snapshot()["pending_nodes"] == [0]
    updates = controller.finalize_pending_learning(reason="unit_test_episode_end")
    assert len(updates) == 1 and updates[0].node_id == 0 and updates[0].terminal
    assert controller.rl_snapshot()["pending_nodes"] == []
    assert controller.segment_context(session_id, 0).status == "TERMINAL_UPDATED"
    assert controller.finalize_pending_learning(reason="second_flush") == []


def test_high_priority_is_present_in_state_and_reward_input() -> None:
    _, controller, _, session_id = run_single(
        2,
        packet_id=1713,
        action=JointAction(2, 15),
        priority=1,
    )
    context = controller.segment_context(session_id, 0)
    assert context.observation.priority == 1
    assert context.state.priority_bin == 1
    assert context.reward_input is not None and context.reward_input.priority == 1
    assert context.reward_breakdown is not None
    assert context.reward_breakdown.priority_delay_multiplier > 1.0


def test_local_outcome_history_updates_after_segment_settlement() -> None:
    _, controller, _, _ = run_single(
        2,
        packet_id=1714,
        action=JointAction(2, 15),
    )
    agent = controller.local_agent(0)
    assert agent.last_reservation_succeeded is True
    assert list(agent.recent_retries) == [0]
    assert agent.recent_mean_retries == 0.0


def test_persistent_conflict_holds_action_and_uses_action_rooted_beb() -> None:
    config = Day17RLPRMACConfig(
        epsilon=0.0,
        retry_limit=1,
        reservation_duration=1.0,
        random_seed=7,
    )
    simulator = Simulator()
    simulator.log_enabled = False
    adjacency = {0: {1}, 1: {0, 2}, 2: {1, 3}, 3: {2, 4}, 4: {3}}
    controller = RLPRMACProtocolController(
        simulator=simulator,
        config=config,
        adjacency=adjacency,
    )
    blocker = Packet(1720, 2, 4, 0.0, route=(2, 3, 4))
    blocker_id = controller.schedule_reservation(blocker, flow_id="day17-blocker")
    simulator.run(until=0.001)
    assert controller.table.get(blocker_id).status == ReservationStatus.ACTIVE

    flow_id = "day17-conflict"
    state = first_state(
        node_id=0,
        packet_id=1721,
        flow_id=flow_id,
        remaining_hops=2,
    )
    prefer_action(
        controller,
        node_id=0,
        state=state,
        action=JointAction(2, 31),
    )
    packet = Packet(1721, 0, 2, simulator.now, route=(0, 1, 2))
    session_id = controller.schedule_end_to_end(packet, flow_id=flow_id, at=simulator.now)
    simulator.run()

    record = controller.end_to_end_records[session_id]
    context = controller.segment_context(session_id, 0)
    retry = controller.retry_records[record.segments[0].retry_id]
    assert record.status == EndToEndStatus.FAILED
    assert packet.status == PacketStatus.DROPPED
    assert context.decision.action == JointAction(2, 31)
    assert [attempt.contention_window for attempt in retry.attempts] == [31, 63]
    assert len({attempt.reservation_id for attempt in retry.attempts}) == 2
    assert all(
        controller.table.get(attempt.reservation_id).requested_hops == 2
        for attempt in retry.attempts
    )
    assert controller.metrics.rl_decisions == 1


def test_retry_exhaustion_settles_negative_terminal_reward() -> None:
    config = Day17RLPRMACConfig(
        epsilon=0.0,
        retry_limit=0,
        reservation_duration=1.0,
        random_seed=7,
    )
    simulator = Simulator()
    simulator.log_enabled = False
    adjacency = {0: {1}, 1: {0, 2}, 2: {1, 3}, 3: {2, 4}, 4: {3}}
    controller = RLPRMACProtocolController(
        simulator=simulator,
        config=config,
        adjacency=adjacency,
    )
    blocker = Packet(1722, 2, 4, 0.0, route=(2, 3, 4))
    controller.schedule_reservation(blocker, flow_id="day17-blocker-fail")
    simulator.run(until=0.001)
    flow_id = "day17-terminal-fail"
    prefer_action(
        controller,
        node_id=0,
        state=first_state(node_id=0, packet_id=1723, flow_id=flow_id, remaining_hops=2),
        action=JointAction(2, 15),
    )
    packet = Packet(1723, 0, 2, simulator.now, route=(0, 1, 2))
    session_id = controller.schedule_end_to_end(packet, flow_id=flow_id, at=simulator.now)
    simulator.run()
    context = controller.segment_context(session_id, 0)
    assert context.reward_breakdown is not None and context.reward_breakdown.reward < 0
    assert context.reward_input is not None
    assert context.reward_input.effective_hops == 0
    assert context.reward_input.pr_nack_count == 1
    assert context.status == "TERMINAL_UPDATED"
    assert context.update is not None and context.update.bootstrap_value == 0.0
    assert controller.local_agent(0).last_reservation_succeeded is False


def test_reward_control_bytes_are_segment_local_and_positive() -> None:
    _, controller, _, session_id = run_single(
        3,
        packet_id=1724,
        action=JointAction(3, 15),
    )
    reward_input = controller.segment_context(session_id, 0).reward_input
    assert reward_input is not None
    assert reward_input.control_bytes > 0
    assert reward_input.payload_bytes > 0
    total_bytes = controller.metrics.summary(controller.table)["total_bytes_sent"]
    assert reward_input.control_bytes < total_bytes


def test_queue_limit_drop_before_decision_does_not_create_fake_rl_action() -> None:
    config = Day17RLPRMACConfig(
        epsilon=0.0,
        queue_limit=1,
        random_seed=7,
    )
    simulator, controller = make_controller(2, config=config)
    flow_id = "day17-queue-limit"
    prefer_action(
        controller,
        node_id=0,
        state=first_state(
            node_id=0,
            packet_id=1730,
            flow_id=flow_id,
            remaining_hops=2,
            queue_limit=1,
        ),
        action=JointAction(2, 15),
    )
    p1 = Packet(1730, 0, 2, 0.0, route=(0, 1, 2))
    p2 = Packet(1731, 0, 2, 0.0, route=(0, 1, 2))
    sid1 = controller.schedule_end_to_end(p1, flow_id=flow_id, at=0.0)
    sid2 = controller.schedule_end_to_end(p2, flow_id=flow_id, at=0.0)
    simulator.run()
    assert controller.end_to_end_records[sid1].status == EndToEndStatus.COMPLETED
    assert controller.end_to_end_records[sid2].status == EndToEndStatus.FAILED
    assert controller.metrics.queue_overflow_drops == 1
    assert controller.metrics.rl_decisions == 1
    assert (sid2, 0) not in controller._segment_contexts


def test_metrics_preserve_day13_delivery_and_add_day17_learning_counts() -> None:
    _, controller, _, _ = run_single(
        2,
        packet_id=1732,
        action=JointAction(2, 15),
    )
    metrics = controller.metrics.summary(controller.table)
    assert metrics["end_to_end_packets_delivered"] == 1
    assert metrics["rl_decisions"] == 1
    assert metrics["rl_segments_settled"] == 1
    assert metrics["q_updates"] == 1
    assert metrics["selected_action_counts"]["K=2,CW=15"] == 1


def test_rl_snapshot_is_auditable_and_contains_no_global_q_table() -> None:
    _, controller, _, session_id = run_single(
        2,
        packet_id=1733,
        action=JointAction(2, 15),
    )
    snapshot = controller.rl_snapshot()
    assert snapshot["decision_epoch"] == DECISION_EPOCH
    assert snapshot["action_lifetime"] == ACTION_LIFETIME
    assert len(snapshot["distributed_agents"]) == 1
    assert len(snapshot["segment_contexts"]) == 1
    assert snapshot["segment_contexts"][0]["session_id"] == session_id
    assert "global_q_table" not in snapshot
    assert "central_controller" not in snapshot


def test_exported_rl_json_is_utf8_parseable() -> None:
    _, controller, _, _ = run_single(
        2,
        packet_id=1734,
        action=JointAction(2, 15),
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "day17.json"
        controller.export_rl_summary_json(path)
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        payload = json.loads(text)
        assert payload["rl"]["protocol_integration_version"] == PROTOCOL_INTEGRATION_VERSION
        assert payload["metrics"]["rl_decisions"] == 1


def test_seeded_controller_is_reproducible() -> None:
    def run_once() -> tuple[tuple[int, int], int, float]:
        simulator, controller = make_controller(3)
        packet = Packet(1735, 0, 3, 0.0, route=(0, 1, 2, 3))
        session_id = controller.schedule_end_to_end(packet, flow_id="day17-seed")
        simulator.run()
        context = controller.segment_context(session_id, 0)
        return (
            context.decision.action.as_tuple(),
            controller.end_to_end_records[session_id].segments[0].access_backoff_slots,
            context.reward_breakdown.reward,
        )

    assert run_once() == run_once()


def test_controller_exposes_no_complete_training_or_central_schedule_api() -> None:
    _, controller = make_controller(3)
    forbidden = (
        "train",
        "fit",
        "run_complete_training",
        "global_schedule",
        "centralized_action",
        "collect_global_state",
    )
    assert all(not hasattr(controller, name) for name in forbidden)


def test_fixed_prmac_baseline_configuration_is_not_mutated_by_rl_action() -> None:
    _, controller, _, _ = run_single(
        3,
        packet_id=1736,
        action=JointAction(3, 31),
    )
    assert controller.config.fixed_k == 2
    assert controller.config.fixed_cw_min == 15


TESTS = [
    test_frozen_versions_and_scopes,
    test_default_action_catalog_is_unchanged,
    test_each_node_owns_an_independent_q_table_and_policy,
    test_decision_is_made_before_initial_access_and_applies_selected_cw,
    test_selected_k_is_applied_exactly_without_silent_truncation,
    test_illegal_large_k_is_masked_at_one_remaining_hop,
    test_default_channel_busy_state_remains_unknown_not_low,
    test_local_busy_provider_is_encoded_without_global_state,
    test_success_reward_is_settled_only_after_release,
    test_final_delivery_creates_immediate_terminal_update,
    test_nonfinal_segment_waits_for_same_node_next_decision,
    test_another_nodes_decision_never_bootstraps_the_first_nodes_q_table,
    test_same_node_next_fifo_head_completes_bootstrapped_update,
    test_explicit_episode_end_flushes_only_remaining_local_pending_items,
    test_high_priority_is_present_in_state_and_reward_input,
    test_local_outcome_history_updates_after_segment_settlement,
    test_persistent_conflict_holds_action_and_uses_action_rooted_beb,
    test_retry_exhaustion_settles_negative_terminal_reward,
    test_reward_control_bytes_are_segment_local_and_positive,
    test_queue_limit_drop_before_decision_does_not_create_fake_rl_action,
    test_metrics_preserve_day13_delivery_and_add_day17_learning_counts,
    test_rl_snapshot_is_auditable_and_contains_no_global_q_table,
    test_exported_rl_json_is_utf8_parseable,
    test_seeded_controller_is_reproducible,
    test_controller_exposes_no_complete_training_or_central_schedule_api,
    test_fixed_prmac_baseline_configuration_is_not_mutated_by_rl_action,
]


def main() -> None:
    for test in TESTS:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"All Day17 protocol-controller tests passed. ({len(TESTS)} tests)")


if __name__ == "__main__":
    main()
