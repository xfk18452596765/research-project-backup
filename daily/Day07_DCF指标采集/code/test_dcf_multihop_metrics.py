"""Tests for Day07 multi-hop DCF and DCF metric collection."""

from __future__ import annotations

import math
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
DAY05_CODE = DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
DAY06_CODE = DAILY_DIR / "Day06_DCF碰撞与重传" / "code"
for path in (CURRENT_DIR, DAY03_CODE, DAY04_CODE, DAY05_CODE, DAY06_CODE):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from node import MacState, Node  # type: ignore  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from dcf_config import DCFConfig  # type: ignore  # noqa: E402
from dcf_multihop_metrics import (  # noqa: E402
    CollisionChannel,
    DCFContentionCoordinator,
    DCFMetricsCollector,
    DCFMultiHopMac,
    DCFMultiHopNetwork,
    SequenceRandom,
)
from main_dcf_multihop_metrics import run_chain_case  # noqa: E402


def test_two_hop_packet_is_forwarded_and_delivered() -> None:
    simulator, channel, _, metrics, _, _, nodes, _, packet = run_chain_case(2)

    assert packet.status == PacketStatus.DELIVERED
    assert packet.current_hop_index == 2
    assert packet.current_node == 2
    assert packet.remaining_hops == 0
    assert metrics.created_packets == 1
    assert metrics.delivered_packets == 1
    assert metrics.successful_hops == 2
    assert all(node.queue_is_empty for node in nodes[:-1])
    assert all(node.mac_state == MacState.IDLE for node in nodes[:-1])
    assert channel.is_idle(simulator.now)


def test_relay_starts_a_fresh_dcf_cycle() -> None:
    _, _, _, _, _, _, _, macs, _ = run_chain_case(2)

    source_events = [record.event for record in macs[0].trace]
    relay_events = [record.event for record in macs[1].trace]

    assert "FORWARDED" in source_events
    assert "FORWARD_ARRIVAL" in relay_events
    for event in ("DIFS_START", "BACKOFF_START", "TX_START", "ACK"):
        assert event in source_events
        assert event in relay_events


def test_two_four_six_hop_delay_accumulates() -> None:
    observed: list[float] = []

    for hop_count in (2, 4, 6):
        _, _, config, _, _, _, _, _, packet = run_chain_case(hop_count)
        assert packet.end_to_end_delay is not None
        expected_one_hop = config.expected_success_delay(
            packet.size_bytes,
            backoff_slots=10,
        )
        expected_total = hop_count * expected_one_hop
        assert math.isclose(packet.end_to_end_delay, expected_total, abs_tol=1e-12)
        observed.append(packet.end_to_end_delay)

    assert observed[0] < observed[1] < observed[2]


def test_metric_counts_match_hop_count_without_contention() -> None:
    hop_count = 4
    _, _, _, metrics, coordinator, _, _, _, packet = run_chain_case(hop_count)

    assert metrics.successful_hops == hop_count
    assert len(metrics.hop_records) == hop_count
    assert metrics.difs_starts == hop_count
    assert metrics.competition_attempts == hop_count
    assert metrics.consumed_backoff_slots == 10 * hop_count
    assert math.isclose(
        metrics.cumulative_backoff_time,
        10 * hop_count * metrics.slot_time,
        abs_tol=1e-15,
    )
    assert metrics.retransmissions == 0
    assert coordinator.collision_count == 0

    packet_summary = metrics.packet_summary(packet.packet_id)
    assert packet_summary["successful_hops"] == hop_count
    assert packet_summary["competition_attempts"] == hop_count
    assert packet_summary["difs_starts"] == hop_count


def test_collision_retry_metrics_remain_available() -> None:
    simulator = Simulator()
    channel = CollisionChannel()
    config = DCFConfig()
    metrics = DCFMetricsCollector(slot_time=config.slot_time)
    coordinator = DCFContentionCoordinator(simulator, channel, config)
    network = DCFMultiHopNetwork(simulator=simulator, metrics=metrics)

    node0 = Node(node_id=0)
    node1 = Node(node_id=1)
    node0.neighbors.add(2)
    node1.neighbors.add(2)

    mac0 = DCFMultiHopMac(
        simulator=simulator,
        node=node0,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 0]),
        coordinator=coordinator,
        network=network,
    )
    mac1 = DCFMultiHopMac(
        simulator=simulator,
        node=node1,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 1]),
        coordinator=coordinator,
        network=network,
    )

    packet0 = Packet(
        packet_id=750,
        source=0,
        destination=2,
        created_at=0.0,
        route=(0, 2),
    )
    packet1 = Packet(
        packet_id=751,
        source=1,
        destination=2,
        created_at=0.0,
        route=(1, 2),
    )

    network.schedule_source_packet(packet0)
    network.schedule_source_packet(packet1)
    simulator.run()
    metrics.capture_coordinator(coordinator)

    assert packet0.status == PacketStatus.DELIVERED
    assert packet1.status == PacketStatus.DELIVERED
    assert metrics.retransmissions == 2
    assert metrics.ack_timeouts == 2
    assert metrics.shared_collision_events == 1
    assert metrics.collided_packet_attempts == 2
    assert metrics.successful_hops == 2
    assert metrics.backoff_freezes >= 1
    assert mac0.current_cw == config.cw_min
    assert mac1.current_cw == config.cw_min


def test_invalid_route_edge_is_rejected() -> None:
    simulator = Simulator()
    channel = CollisionChannel()
    config = DCFConfig()
    metrics = DCFMetricsCollector(slot_time=config.slot_time)
    coordinator = DCFContentionCoordinator(simulator, channel, config)
    network = DCFMultiHopNetwork(simulator=simulator, metrics=metrics)
    node = Node(node_id=0)

    DCFMultiHopMac(
        simulator=simulator,
        node=node,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0]),
        coordinator=coordinator,
        network=network,
    )

    packet = Packet(
        packet_id=760,
        source=0,
        destination=1,
        created_at=0.0,
        route=(0, 1),
    )

    try:
        network.schedule_source_packet(packet)
    except ValueError as exc:
        assert "neighbor link" in str(exc)
    else:
        raise AssertionError("A route containing a non-neighbor edge must be rejected.")


def run_all_tests() -> None:
    tests = [
        test_two_hop_packet_is_forwarded_and_delivered,
        test_relay_starts_a_fresh_dcf_cycle,
        test_two_four_six_hop_delay_accumulates,
        test_metric_counts_match_hop_count_without_contention,
        test_collision_retry_metrics_remain_available,
        test_invalid_route_edge_is_rejected,
    ]

    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")

    print("\nAll Day07 multi-hop DCF and metric-collection tests passed.")


if __name__ == "__main__":
    run_all_tests()
