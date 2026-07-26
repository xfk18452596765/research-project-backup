"""Tests for Day11 Fixed-PRMAC continuous DATA forwarding and per-hop H_ACK."""
from __future__ import annotations

import math
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY10_CODE = DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

_import_paths = [CURRENT_DIR, DAY10_CODE, DAY09_CODE, DAY03_CODE]
for path in _import_paths:
    path_text = str(path)
    while path_text in sys.path:
        sys.path.remove(path_text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_messages import PRMACFrameType, ReservationStatus  # noqa: E402
from fixed_prmac_forwarding import (  # noqa: E402
    Day11FixedPRMACConfig,
    FixedPRMACForwardingController,
    SegmentForwardingStatus,
)


def build_controller(*, log_enabled: bool = False):
    simulator = Simulator()
    simulator.log_enabled = log_enabled
    adjacency = {
        0: {1},
        1: {0, 2, 4},
        2: {1, 3},
        3: {1, 2, 4},
        4: {3, 5},
        5: {4, 6},
        6: {5},
    }
    controller = FixedPRMACForwardingController(
        simulator=simulator,
        adjacency=adjacency,
    )
    return simulator, controller


def make_packet(
    *,
    packet_id: int,
    route: tuple[int, ...],
    current_hop_index: int = 0,
    size_bytes: int = 1024,
    priority: int = 1,
) -> Packet:
    return Packet(
        packet_id=packet_id,
        source=route[0],
        destination=route[-1],
        created_at=0.0,
        size_bytes=size_bytes,
        priority=priority,
        route=route,
        current_hop_index=current_hop_index,
    )


def activate(
    simulator: Simulator,
    controller: FixedPRMACForwardingController,
    packet: Packet,
    *,
    flow_id: str,
) -> str:
    reservation_id = controller.schedule_reservation(packet, flow_id=flow_id)
    simulator.run()
    assert controller.table.get(reservation_id).status == ReservationStatus.ACTIVE
    return reservation_id


def test_day11_phy_defaults_match_existing_dcf_baseline() -> None:
    config = Day11FixedPRMACConfig()
    assert config.data_rate_bps == 2_000_000.0
    assert config.basic_rate_bps == 1_000_000.0
    assert config.data_mac_header_bytes == 34
    assert config.h_ack_size_bytes == 14
    assert math.isclose(config.data_tx_time(1024), (1024 + 34) * 8 / 2_000_000)
    assert math.isclose(config.h_ack_tx_time, 14 * 8 / 1_000_000)


def test_k2_active_reservation_forwards_two_data_and_two_h_ack() -> None:
    simulator, controller = build_controller(log_enabled=True)
    packet = make_packet(packet_id=1200, route=(0, 1, 2, 3, 4))
    reservation_id = activate(
        simulator,
        controller,
        packet,
        flow_id="flow-k2-forward",
    )

    transfer_id = controller.schedule_reserved_forwarding(reservation_id, packet)
    simulator.run()

    forwarding = controller.forwarding_records[transfer_id]
    assert forwarding.status == SegmentForwardingStatus.COMPLETED
    assert packet.current_hop_index == 2
    assert packet.current_node == 2
    assert packet.status == PacketStatus.FORWARDED
    assert controller.table.get(reservation_id).status == ReservationStatus.ACTIVE

    data_frames = [
        frame
        for frame in controller.frames
        if frame.packet_id == packet.packet_id
        and frame.frame_type == PRMACFrameType.DATA
    ]
    h_ack_frames = [
        frame
        for frame in controller.frames
        if frame.packet_id == packet.packet_id
        and frame.frame_type == PRMACFrameType.H_ACK
    ]
    assert [(frame.sender, frame.receiver) for frame in data_frames] == [(0, 1), (1, 2)]
    assert [(frame.sender, frame.receiver) for frame in h_ack_frames] == [(1, 0), (2, 1)]
    assert controller.metrics.data_frames_sent == 2
    assert controller.metrics.h_ack_frames_sent == 2
    assert controller.metrics.forwarded_hops == 2
    assert controller.metrics.completed_segments == 1
    assert "GENERIC" not in "\n".join(simulator.log_records)


def test_next_data_waits_for_previous_h_ack_reception() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1210, route=(0, 1, 2, 3))
    reservation_id = activate(simulator, controller, packet, flow_id="flow-order")
    controller.schedule_reserved_forwarding(reservation_id, packet)
    simulator.run()

    trace = [
        item
        for item in controller.trace
        if item.reservation_id == reservation_id
        and item.event in {"DATA_TX", "DATA_RX", "H_ACK_TX", "H_ACK_RX"}
    ]
    assert [item.event for item in trace] == [
        "DATA_TX",
        "DATA_RX",
        "H_ACK_TX",
        "H_ACK_RX",
        "DATA_TX",
        "DATA_RX",
        "H_ACK_TX",
        "H_ACK_RX",
    ]
    first_h_ack_rx = trace[3]
    second_data_tx = trace[4]
    assert second_data_tx.time > first_h_ack_rx.time
    assert math.isclose(
        second_data_tx.time - first_h_ack_rx.time,
        controller.config.sifs_time,
        abs_tol=1e-15,
    )


def test_remaining_one_hop_uses_one_data_and_one_h_ack() -> None:
    simulator, controller = build_controller()
    packet = make_packet(
        packet_id=1220,
        route=(0, 1, 2),
        current_hop_index=1,
    )
    reservation_id = activate(
        simulator,
        controller,
        packet,
        flow_id="flow-one-hop",
    )
    record = controller.table.get(reservation_id)
    assert record.effective_hops == 1

    transfer_id = controller.schedule_reserved_forwarding(reservation_id, packet)
    simulator.run()

    forwarding = controller.forwarding_records[transfer_id]
    assert forwarding.status == SegmentForwardingStatus.COMPLETED
    assert packet.current_node == 2
    assert packet.status == PacketStatus.DELIVERED
    assert packet.delivered_at is not None
    assert controller.metrics.data_frames_sent == 1
    assert controller.metrics.h_ack_frames_sent == 1


def test_long_route_stops_at_reserved_segment_endpoint() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1230, route=(0, 1, 2, 3, 4, 5, 6))
    reservation_id = activate(simulator, controller, packet, flow_id="flow-stop-k2")
    controller.schedule_reserved_forwarding(reservation_id, packet)
    simulator.run()

    assert packet.current_hop_index == 2
    assert packet.current_node == 2
    assert packet.remaining_hops == 4
    assert packet.status == PacketStatus.FORWARDED
    forwarding_events = [
        item.event
        for item in controller.trace
        if item.reservation_id == reservation_id
        and item.event.startswith("SEGMENT_FORWARD")
    ]
    assert forwarding_events == ["SEGMENT_FORWARD_START", "SEGMENT_FORWARD_COMPLETE"]


def test_non_active_reservations_cannot_schedule_data() -> None:
    # PENDING
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1240, route=(0, 1, 2))
    pending_id = controller.schedule_reservation(packet, flow_id="flow-pending", at=1.0)
    try:
        controller.schedule_reserved_forwarding(pending_id, packet)
    except RuntimeError as exc:
        assert "ACTIVE" in str(exc)
    else:
        raise AssertionError("PENDING reservation must not forward DATA.")

    # RELEASED
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1241, route=(0, 1, 2))
    released_id = activate(simulator, controller, packet, flow_id="flow-released")
    controller.schedule_release(released_id)
    simulator.run()
    assert controller.table.get(released_id).status == ReservationStatus.RELEASED
    try:
        controller.schedule_reserved_forwarding(released_id, packet)
    except RuntimeError as exc:
        assert "ACTIVE" in str(exc)
    else:
        raise AssertionError("RELEASED reservation must not forward DATA.")

    # EXPIRED
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1242, route=(0, 1, 2))
    expired_id = activate(simulator, controller, packet, flow_id="flow-expired")
    expired = controller.table.get(expired_id)
    assert expired.expires_at is not None
    controller.expire_reservations(now=expired.expires_at)
    assert expired.status == ReservationStatus.EXPIRED
    try:
        controller.schedule_reserved_forwarding(expired_id, packet)
    except RuntimeError as exc:
        assert "ACTIVE" in str(exc)
    else:
        raise AssertionError("EXPIRED reservation must not forward DATA.")


def test_rejected_reservation_cannot_schedule_data() -> None:
    simulator, controller = build_controller()
    existing_packet = make_packet(packet_id=1250, route=(2, 3, 4))
    activate(simulator, controller, existing_packet, flow_id="flow-existing")

    rejected_packet = make_packet(packet_id=1251, route=(0, 1, 2))
    rejected_id = controller.schedule_reservation(
        rejected_packet,
        flow_id="flow-rejected",
    )
    simulator.run()
    assert controller.table.get(rejected_id).status == ReservationStatus.REJECTED
    try:
        controller.schedule_reserved_forwarding(rejected_id, rejected_packet)
    except RuntimeError as exc:
        assert "ACTIVE" in str(exc)
    else:
        raise AssertionError("REJECTED reservation must not forward DATA.")


def test_packet_must_match_reservation_identity_route_and_segment_start() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1260, route=(0, 1, 2, 3))
    reservation_id = activate(simulator, controller, packet, flow_id="flow-match")

    wrong_id = make_packet(packet_id=1261, route=(0, 1, 2, 3))
    try:
        controller.schedule_reserved_forwarding(reservation_id, wrong_id)
    except ValueError as exc:
        assert "identifier" in str(exc)
    else:
        raise AssertionError("Mismatched packet_id must be rejected.")

    wrong_route = make_packet(packet_id=1260, route=(0, 1, 4))
    try:
        controller.schedule_reserved_forwarding(reservation_id, wrong_route)
    except ValueError as exc:
        assert "route" in str(exc)
    else:
        raise AssertionError("Mismatched route must be rejected.")

    packet.current_hop_index = 1
    try:
        controller.schedule_reserved_forwarding(reservation_id, packet)
    except ValueError as exc:
        assert "current_hop_index" in str(exc)
    else:
        raise AssertionError("Wrong segment start must be rejected.")


def test_forwarding_delay_and_byte_metrics_match_analytical_values() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1270, route=(0, 1, 2, 3), size_bytes=1024)
    reservation_id = activate(simulator, controller, packet, flow_id="flow-metrics")
    transfer_id = controller.schedule_reserved_forwarding(reservation_id, packet)
    simulator.run()

    forwarding = controller.forwarding_records[transfer_id]
    expected_delay = controller.config.estimated_segment_forwarding_time(
        packet.size_bytes,
        2,
    )
    assert forwarding.forwarding_delay is not None
    assert math.isclose(
        forwarding.forwarding_delay,
        expected_delay,
        abs_tol=1e-15,
    )
    assert controller.metrics.data_bytes_sent == 2 * (1024 + 34)
    assert controller.metrics.h_ack_bytes_sent == 2 * 14

    summary = controller.metrics.summary(controller.table)
    assert summary["completed_segments"] == 1
    assert summary["forwarded_hops"] == 2
    assert summary["data_frames_sent"] == 2
    assert summary["h_ack_frames_sent"] == 2
    assert summary["total_frames_sent"] == 8
    assert summary["total_bytes_sent"] == 120 + 2 * 1058 + 2 * 14
    assert math.isclose(
        float(summary["average_segment_forwarding_delay"]),
        expected_delay,
        abs_tol=1e-15,
    )


def test_reservation_window_must_cover_complete_segment() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1280, route=(0, 1, 2, 3))
    reservation_id = activate(simulator, controller, packet, flow_id="flow-window")
    record = controller.table.get(reservation_id)
    assert record.expires_at is not None

    too_late = record.expires_at - 1e-6
    try:
        controller.schedule_reserved_forwarding(
            reservation_id,
            packet,
            at=too_late,
        )
    except RuntimeError as exc:
        assert "too short" in str(exc)
    else:
        raise AssertionError("Too-short reservation remainder must be rejected.")


def run_all_tests() -> None:
    tests = [
        test_day11_phy_defaults_match_existing_dcf_baseline,
        test_k2_active_reservation_forwards_two_data_and_two_h_ack,
        test_next_data_waits_for_previous_h_ack_reception,
        test_remaining_one_hop_uses_one_data_and_one_h_ack,
        test_long_route_stops_at_reserved_segment_endpoint,
        test_non_active_reservations_cannot_schedule_data,
        test_rejected_reservation_cannot_schedule_data,
        test_packet_must_match_reservation_identity_route_and_segment_start,
        test_forwarding_delay_and_byte_metrics_match_analytical_values,
        test_reservation_window_must_cover_complete_segment,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("\nAll Day11 Fixed-PRMAC continuous-forwarding tests passed.")


if __name__ == "__main__":
    run_all_tests()
