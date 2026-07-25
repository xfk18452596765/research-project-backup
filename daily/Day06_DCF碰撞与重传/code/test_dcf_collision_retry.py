"""Tests for Day06 collision, ACK timeout, BEB and retry."""

from __future__ import annotations

import math
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
DAY05_CODE = DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
for path in (CURRENT_DIR, DAY03_CODE, DAY04_CODE, DAY05_CODE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from metrics import MetricsCollector
from node import MacState, Node
from packet import Packet, PacketStatus
from simulator import Simulator
from dcf_config import DCFConfig
from dcf_collision_mac import (
    CollisionChannel,
    DCFContentionCoordinator,
    DCFContentionMac,
    SequenceRandom,
)



def get_retry_metric_count(metrics: MetricsCollector) -> int:
    """Read the retry counter without assuming one fixed Day03 field name."""

    # Common public counter names used by different MetricsCollector versions.
    for name in (
        "total_retries",
        "retransmissions",
        "retry_count",
        "retries",
        "total_retransmissions",
    ):
        value = getattr(metrics, name, None)
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except TypeError:
                continue
        if isinstance(value, (int, float)):
            return int(value)

    # Some versions expose counters through summary()/get_summary().
    for method_name in ("summary", "get_summary"):
        method = getattr(metrics, method_name, None)
        if not callable(method):
            continue
        try:
            summary = method()
        except TypeError:
            continue
        if isinstance(summary, dict):
            for key in (
                "total_retries",
                "retransmissions",
                "retry_count",
                "retries",
                "total_retransmissions",
            ):
                value = summary.get(key)
                if isinstance(value, (int, float)):
                    return int(value)

    # Last compatibility fallback: inspect numeric instance fields containing
    # retry/retransmission wording.
    for name, value in vars(metrics).items():
        normalized = name.lower()
        if (
            ("retry" in normalized or "retrans" in normalized)
            and isinstance(value, (int, float))
        ):
            return int(value)

    raise AssertionError(
        "Unable to locate the retry counter in MetricsCollector. "
        f"Available fields: {sorted(vars(metrics).keys())}"
    )

def build_two_station_case(*, retry_limit: int = 7):
    simulator = Simulator()
    channel = CollisionChannel()
    metrics = MetricsCollector()
    config = DCFConfig(retry_limit=retry_limit)
    coordinator = DCFContentionCoordinator(simulator, channel, config)

    node0 = Node(node_id=0)
    node1 = Node(node_id=1)
    node0.neighbors.add(2)
    node1.neighbors.add(2)

    # First attempt: both 0 -> collision.
    # Second attempt: node0=0, node1=1 -> node0 succeeds first; node1 freezes
    # one remaining slot and sends after node0's ACK.
    mac0 = DCFContentionMac(
        simulator=simulator,
        node=node0,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 0]),
        coordinator=coordinator,
    )
    mac1 = DCFContentionMac(
        simulator=simulator,
        node=node1,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 1]),
        coordinator=coordinator,
    )
    packet0 = Packet(
        packet_id=600,
        source=0,
        destination=2,
        created_at=0.0,
        size_bytes=1024,
        route=(0, 2),
    )
    packet1 = Packet(
        packet_id=601,
        source=1,
        destination=2,
        created_at=0.0,
        size_bytes=1024,
        route=(1, 2),
    )
    return simulator, channel, metrics, coordinator, node0, node1, mac0, mac1, packet0, packet1


def run_two_station_case(*, retry_limit: int = 7):
    case = build_two_station_case(retry_limit=retry_limit)
    simulator, _, _, _, _, _, mac0, mac1, packet0, packet1 = case
    mac0.schedule_packet_arrival(packet0)
    mac1.schedule_packet_arrival(packet1)
    simulator.run()
    return case


def test_single_station_keeps_day04_success_delay() -> None:
    simulator = Simulator()
    channel = CollisionChannel()
    metrics = MetricsCollector()
    config = DCFConfig()
    coordinator = DCFContentionCoordinator(simulator, channel, config)
    node = Node(node_id=0)
    node.neighbors.add(2)
    mac = DCFContentionMac(
        simulator=simulator,
        node=node,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([10]),
        coordinator=coordinator,
    )
    packet = Packet(
        packet_id=610,
        source=0,
        destination=2,
        created_at=0.0,
        size_bytes=1024,
        route=(0, 2),
    )
    mac.schedule_packet_arrival(packet)
    simulator.run()
    assert packet.status == PacketStatus.DELIVERED
    assert packet.end_to_end_delay is not None
    assert math.isclose(packet.end_to_end_delay, 0.004606, abs_tol=1e-12)
    assert coordinator.collision_count == 0


def test_same_slot_attempts_create_one_collision() -> None:
    _, _, _, coordinator, _, _, mac0, mac1, _, _ = run_two_station_case()
    assert coordinator.collision_count == 1
    assert mac0.collision_attempts == 1
    assert mac1.collision_attempts == 1
    assert "COLLISION" in [record.event for record in mac0.trace]
    assert "COLLISION" in [record.event for record in mac1.trace]


def test_collision_causes_ack_timeout_retry_and_beb() -> None:
    _, _, metrics, _, _, _, mac0, mac1, packet0, packet1 = run_two_station_case()
    assert packet0.retries == 1
    assert packet1.retries == 1
    assert mac0.max_cw_observed == 31
    assert mac1.max_cw_observed == 31
    assert mac0.current_cw == mac0.config.cw_min
    assert mac1.current_cw == mac1.config.cw_min
    assert get_retry_metric_count(metrics) == 2

    for mac in (mac0, mac1):
        events = [record.event for record in mac.trace]
        assert "ACK_TIMEOUT" in events
        update = next(record for record in mac.trace if record.event == "CW_UPDATE")
        assert "old=15" in update.detail
        assert "new=31" in update.detail


def test_two_stations_eventually_deliver_after_different_retry_backoffs() -> None:
    simulator, channel, metrics, coordinator, node0, node1, mac0, mac1, packet0, packet1 = run_two_station_case()
    assert packet0.status == PacketStatus.DELIVERED
    assert packet1.status == PacketStatus.DELIVERED
    assert node0.queue_is_empty and node1.queue_is_empty
    assert node0.mac_state == MacState.IDLE
    assert node1.mac_state == MacState.IDLE
    assert channel.is_idle(simulator.now)
    assert metrics.created_packets == 2
    assert metrics.delivered_packets == 2
    assert metrics.dropped_packets == 0
    assert coordinator.successful_exchange_count == 2

    freeze = next(record for record in mac1.trace if record.event == "BACKOFF_FREEZE")
    resume = next(record for record in mac1.trace if record.event == "BACKOFF_RESUME")
    assert "remaining_slots=1" in freeze.detail
    assert "remaining_slots=1" in resume.detail
    assert packet0.end_to_end_delay is not None
    assert packet1.end_to_end_delay is not None
    assert math.isclose(packet0.end_to_end_delay, 0.008812, abs_tol=1e-12)
    assert math.isclose(packet1.end_to_end_delay, 0.013238, abs_tol=1e-12)


def test_retry_limit_zero_drops_both_collided_packets() -> None:
    simulator = Simulator()
    channel = CollisionChannel()
    metrics = MetricsCollector()
    config = DCFConfig(retry_limit=0)
    coordinator = DCFContentionCoordinator(simulator, channel, config)
    nodes = [Node(node_id=0), Node(node_id=1)]
    macs = [
        DCFContentionMac(
            simulator=simulator,
            node=node,
            channel=channel,
            metrics=metrics,
            config=config,
            rng=SequenceRandom([0]),
            coordinator=coordinator,
        )
        for node in nodes
    ]
    packets = [
        Packet(
            packet_id=620 + index,
            source=index,
            destination=2,
            created_at=0.0,
            size_bytes=1024,
            route=(index, 2),
        )
        for index in range(2)
    ]
    for mac, packet in zip(macs, packets):
        mac.schedule_packet_arrival(packet)
    simulator.run()

    assert metrics.created_packets == 2
    assert metrics.delivered_packets == 0
    assert metrics.dropped_packets == 2
    assert all(node.queue_is_empty for node in nodes)
    assert all(mac.phase == mac.PHASE_IDLE for mac in macs)
    assert channel.is_idle(simulator.now)
    assert all("DROPPED" in [r.event for r in mac.trace] for mac in macs)


def run_all_tests() -> None:
    tests = [
        test_single_station_keeps_day04_success_delay,
        test_same_slot_attempts_create_one_collision,
        test_collision_causes_ack_timeout_retry_and_beb,
        test_two_stations_eventually_deliver_after_different_retry_backoffs,
        test_retry_limit_zero_drops_both_collided_packets,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("\nAll Day06 DCF collision and retransmission tests passed.")


if __name__ == "__main__":
    run_all_tests()
