"""Tests for Day05 busy-channel deferral and backoff freeze/resume."""

from __future__ import annotations

import math
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
for path in (CURRENT_DIR, DAY03_CODE, DAY04_CODE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from channel import Channel
from metrics import MetricsCollector
from node import MacState, Node
from packet import Packet, PacketStatus
from simulator import Simulator
from dcf_config import DCFConfig
from dcf_busy_mac import DCFBusyMac


def build_case(seed: int = 7):
    simulator = Simulator()
    channel = Channel()
    metrics = MetricsCollector()
    node = Node(node_id=0)
    node.neighbors.add(1)
    mac = DCFBusyMac(
        simulator=simulator,
        node=node,
        channel=channel,
        metrics=metrics,
        config=DCFConfig(random_seed=seed),
    )
    packet = Packet(
        packet_id=500,
        source=0,
        destination=1,
        created_at=0.0,
        size_bytes=1024,
        route=(0, 1),
    )
    return simulator, channel, metrics, node, mac, packet


def assert_delivered(simulator, channel, metrics, node, mac, packet) -> None:
    assert packet.status == PacketStatus.DELIVERED
    assert node.queue_is_empty
    assert node.mac_state == MacState.IDLE
    assert channel.is_idle(simulator.now)
    assert metrics.created_packets == 1
    assert metrics.delivered_packets == 1
    assert metrics.dropped_packets == 0
    assert packet.retries == 0
    assert mac.phase == mac.PHASE_IDLE


def test_no_busy_remains_compatible_with_day04_delay() -> None:
    simulator, channel, metrics, node, mac, packet = build_case()
    mac.schedule_packet_arrival(packet)
    simulator.run()
    assert_delivered(simulator, channel, metrics, node, mac, packet)
    assert packet.end_to_end_delay is not None
    assert math.isclose(packet.end_to_end_delay, 0.004606, abs_tol=1e-12)


def test_busy_at_arrival_defers_until_idle_then_difs() -> None:
    simulator, channel, metrics, node, mac, packet = build_case()
    mac.schedule_external_busy(start_time=0.0, duration=100e-6)
    mac.schedule_packet_arrival(packet)
    simulator.run()
    assert_delivered(simulator, channel, metrics, node, mac, packet)

    events = [record.event for record in mac.trace]
    assert events[0:3] == ["PACKET_ARRIVAL", "CHANNEL_BUSY_WAIT", "EXTERNAL_BUSY_END"]
    difs_start = next(record for record in mac.trace if record.event == "DIFS_START")
    assert math.isclose(difs_start.time, 100e-6, abs_tol=1e-12)
    assert packet.end_to_end_delay is not None
    assert math.isclose(packet.end_to_end_delay, 0.004706, abs_tol=1e-12)


def test_busy_during_difs_restarts_full_difs() -> None:
    simulator, channel, metrics, node, mac, packet = build_case()
    mac.schedule_packet_arrival(packet)
    mac.schedule_external_busy(start_time=20e-6, duration=100e-6)
    simulator.run()
    assert_delivered(simulator, channel, metrics, node, mac, packet)

    events = [record.event for record in mac.trace]
    assert "DIFS_INTERRUPTED" in events
    difs_starts = [record.time for record in mac.trace if record.event == "DIFS_START"]
    assert len(difs_starts) == 2
    assert math.isclose(difs_starts[0], 0.0, abs_tol=1e-12)
    assert math.isclose(difs_starts[1], 120e-6, abs_tol=1e-12)
    assert packet.end_to_end_delay is not None
    assert math.isclose(packet.end_to_end_delay, 0.004726, abs_tol=1e-12)


def test_busy_during_backoff_freezes_and_resumes_remaining_slots() -> None:
    simulator, channel, metrics, node, mac, packet = build_case()
    mac.schedule_packet_arrival(packet)
    mac.schedule_external_busy(start_time=100e-6, duration=100e-6)
    simulator.run()
    assert_delivered(simulator, channel, metrics, node, mac, packet)

    freeze = next(record for record in mac.trace if record.event == "BACKOFF_FREEZE")
    resume = next(record for record in mac.trace if record.event == "BACKOFF_RESUME")
    assert "remaining_slots=8" in freeze.detail
    assert "remaining_slots=8" in resume.detail

    difs_starts = [record.time for record in mac.trace if record.event == "DIFS_START"]
    assert len(difs_starts) == 2
    assert math.isclose(difs_starts[1], 200e-6, abs_tol=1e-12)

    tx_start = next(record.time for record in mac.trace if record.event == "TX_START")
    assert math.isclose(tx_start, 410e-6, abs_tol=1e-12)
    assert packet.end_to_end_delay is not None
    assert math.isclose(packet.end_to_end_delay, 0.004766, abs_tol=1e-12)


def test_day05_does_not_increment_retry_or_cw() -> None:
    simulator, _, _, _, mac, packet = build_case()
    mac.schedule_packet_arrival(packet)
    mac.schedule_external_busy(start_time=100e-6, duration=100e-6)
    simulator.run()
    assert packet.retries == 0
    assert mac.current_cw == mac.config.cw_min


def run_all_tests() -> None:
    tests = [
        test_no_busy_remains_compatible_with_day04_delay,
        test_busy_at_arrival_defers_until_idle_then_difs,
        test_busy_during_difs_restarts_full_difs,
        test_busy_during_backoff_freezes_and_resumes_remaining_slots,
        test_day05_does_not_increment_retry_or_cw,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("\nAll Day05 DCF busy-channel and backoff-freeze tests passed.")


if __name__ == "__main__":
    run_all_tests()
