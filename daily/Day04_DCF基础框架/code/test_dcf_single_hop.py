"""Tests for Day04 minimum single-hop DCF."""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAY03_CODE = CURRENT_DIR.parents[1] / "Day03_仿真架构与事件设计" / "code"
for path in (CURRENT_DIR, DAY03_CODE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from channel import Channel
from metrics import MetricsCollector
from node import MacState, Node
from packet import Packet, PacketStatus
from simulator import Simulator

from dcf_config import DCFConfig
from dcf_mac import DCFMac


def get_delivery_ratio(metrics: MetricsCollector) -> float:
    """Read delivery ratio without assuming Day03 exposes it as a property."""
    value = getattr(metrics, "delivery_ratio", None)
    if value is not None:
        return float(value() if callable(value) else value)

    for method_name in ("summary", "get_summary", "report"):
        method = getattr(metrics, method_name, None)
        if not callable(method):
            continue
        result = method()
        if isinstance(result, dict):
            for key in ("delivery_ratio", "packet_delivery_ratio", "delivery_rate"):
                if key in result:
                    return float(result[key])

    created = int(getattr(metrics, "created_packets", 0))
    delivered = int(getattr(metrics, "delivered_packets", 0))
    return delivered / created if created > 0 else 0.0


def build_case(seed: int = 7) -> tuple[Simulator, Channel, MetricsCollector, Node, DCFMac, Packet]:
    simulator = Simulator()
    channel = Channel()
    metrics = MetricsCollector()
    node = Node(node_id=0)
    node.neighbors.add(1)
    config = DCFConfig(random_seed=seed)
    mac = DCFMac(simulator, node, channel, metrics, config)
    packet = Packet(
        packet_id=100,
        source=0,
        destination=1,
        created_at=0.0,
        size_bytes=1024,
        route=(0, 1),
    )
    return simulator, channel, metrics, node, mac, packet


def test_config_duration_formula() -> None:
    config = DCFConfig()
    assert math.isclose(config.data_tx_time(1024), (1024 + 34) * 8 / 2_000_000)
    assert math.isclose(config.ack_tx_time, 14 * 8 / 1_000_000)


def test_deterministic_random_backoff() -> None:
    simulator, _, _, _, mac, packet = build_case(seed=7)
    mac.schedule_packet_arrival(packet)
    simulator.run()
    backoff_start = next(item for item in mac.trace if item.event == "BACKOFF_START")
    assert "slots=10" in backoff_start.detail


def test_single_packet_reaches_delivered_state() -> None:
    simulator, channel, metrics, node, mac, packet = build_case(seed=7)
    mac.schedule_packet_arrival(packet)
    simulator.run()

    assert packet.status == PacketStatus.DELIVERED
    assert packet.current_node == 1
    assert packet.remaining_hops == 0
    assert packet.delivered_at is not None
    assert node.queue_is_empty
    assert node.mac_state == MacState.IDLE
    assert channel.is_idle(simulator.now)
    assert metrics.created_packets == 1
    assert metrics.delivered_packets == 1
    assert metrics.dropped_packets == 0
    assert math.isclose(get_delivery_ratio(metrics), 1.0)


def test_event_chain_order() -> None:
    simulator, _, _, _, mac, packet = build_case(seed=7)
    mac.schedule_packet_arrival(packet)
    simulator.run()

    assert [item.event for item in mac.trace] == [
        "PACKET_ARRIVAL",
        "DIFS_START",
        "DIFS_END",
        "BACKOFF_START",
        "BACKOFF_EXPIRE",
        "TX_START",
        "TX_END",
        "ACK",
        "DELIVERED",
    ]


def test_delivery_time_matches_analytical_sum() -> None:
    simulator, _, _, _, mac, packet = build_case(seed=7)
    mac.schedule_packet_arrival(packet)
    simulator.run()

    expected_slots = random.Random(7).randint(0, mac.config.cw_min)
    expected = mac.config.expected_success_delay(packet.size_bytes, expected_slots)
    assert packet.end_to_end_delay is not None
    assert math.isclose(packet.end_to_end_delay, expected, rel_tol=0.0, abs_tol=1e-12)


def test_existing_enqueue_call_is_supported() -> None:
    simulator, _, metrics, node, mac, packet = build_case(seed=7)
    assert node.enqueue(packet)
    mac.schedule_packet_arrival(packet)
    simulator.run()

    assert packet.status == PacketStatus.DELIVERED
    assert metrics.created_packets == 1
    assert metrics.delivered_packets == 1


def run_all_tests() -> None:
    tests = [
        test_config_duration_formula,
        test_deterministic_random_backoff,
        test_single_packet_reaches_delivered_state,
        test_event_chain_order,
        test_delivery_time_matches_analytical_sum,
        test_existing_enqueue_call_is_supported,
    ]
    for test in tests:
        test()
    print("All Day04 minimum single-hop DCF tests passed.")


if __name__ == "__main__":
    run_all_tests()
