"""Tests for Day09 Fixed-PRMAC messages and successful reservation setup."""

from __future__ import annotations

import math
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

for path in (CURRENT_DIR, DAY03_CODE):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402

from fixed_prmac_messages import PRMACFrameType, ReservationStatus
from fixed_prmac_reservation import (
    FixedPRMACConfig,
    FixedPRMACReservationController,
)


def build_controller(*, log_enabled: bool = False):
    simulator = Simulator()
    simulator.log_enabled = log_enabled
    adjacency = {
        0: {1},
        1: {2},
        2: {3},
        3: {4},
    }
    controller = FixedPRMACReservationController(
        simulator=simulator,
        adjacency=adjacency,
    )
    return simulator, controller


def make_packet(
    *,
    packet_id: int = 900,
    route: tuple[int, ...] = (0, 1, 2, 3),
    current_hop_index: int = 0,
) -> Packet:
    return Packet(
        packet_id=packet_id,
        source=route[0],
        destination=route[-1],
        created_at=0.0,
        priority=1,
        route=route,
        current_hop_index=current_hop_index,
    )


def test_fixed_baseline_parameters_are_frozen() -> None:
    config = FixedPRMACConfig()
    assert config.fixed_k == 2
    assert config.fixed_cw_min == 15
    assert config.reservation_duration > 0


def test_k2_pr_req_and_reverse_pr_ack_activate_reservation() -> None:
    simulator, controller = build_controller(log_enabled=True)
    packet = make_packet()

    reservation_id = controller.schedule_reservation(
        packet,
        flow_id="flow-A",
    )
    simulator.run()

    record = controller.table.get(reservation_id)
    assert record.status == ReservationStatus.ACTIVE
    assert record.requested_hops == 2
    assert record.effective_hops == 2
    assert [(link.sender, link.receiver) for link in record.reserved_links] == [
        (0, 1),
        (1, 2),
    ]
    assert record.initiator == 0
    assert record.endpoint == 2
    assert packet.current_hop_index == 0
    assert packet.status == PacketStatus.CREATED

    events = [item.event for item in controller.trace]
    assert events == [
        "RESERVATION_START",
        "PR_REQ_TX",
        "PR_REQ_RX",
        "PR_REQ_TX",
        "PR_REQ_RX",
        "PR_ACK_TX",
        "PR_ACK_RX",
        "PR_ACK_TX",
        "PR_ACK_RX",
        "RESERVATION_ACTIVE",
    ]

    log_text = "\n".join(simulator.log_records)
    for event_name in (
        "RESERVATION_START",
        "PR_REQ_TX",
        "PR_REQ_RX",
        "PR_ACK_TX",
        "PR_ACK_RX",
    ):
        assert event_name in log_text
    assert "GENERIC" not in log_text


def test_remaining_one_hop_truncates_effective_k() -> None:
    simulator, controller = build_controller()
    packet = make_packet(
        packet_id=901,
        route=(0, 1, 2),
        current_hop_index=1,
    )

    reservation_id = controller.schedule_reservation(packet)
    simulator.run()
    record = controller.table.get(reservation_id)

    assert record.status == ReservationStatus.ACTIVE
    assert record.requested_hops == 2
    assert record.effective_hops == 1
    assert [(link.sender, link.receiver) for link in record.reserved_links] == [
        (1, 2)
    ]
    assert record.initiator == 1
    assert record.endpoint == 2


def test_control_frames_preserve_required_fields_and_overhead() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=902)

    controller.schedule_reservation(packet, flow_id="flow-fields")
    simulator.run()

    assert len(controller.frames) == 4
    assert [frame.frame_type for frame in controller.frames] == [
        PRMACFrameType.PR_REQ,
        PRMACFrameType.PR_REQ,
        PRMACFrameType.PR_ACK,
        PRMACFrameType.PR_ACK,
    ]

    for frame in controller.frames:
        assert frame.flow_id == "flow-fields"
        assert frame.packet_id == packet.packet_id
        assert frame.path == tuple(packet.route)
        assert frame.segment_start_index == 0
        assert frame.requested_hops == 2
        assert frame.effective_hops == 2
        assert frame.priority == packet.priority
        assert math.isclose(
            frame.duration,
            controller.config.reservation_duration,
            abs_tol=0.0,
        )

    ack_frames = [
        frame
        for frame in controller.frames
        if frame.frame_type == PRMACFrameType.PR_ACK
    ]
    assert all(len(frame.reserved_links) == 2 for frame in ack_frames)

    summary = controller.metrics.summary(controller.table)
    expected_bytes = (
        2 * controller.config.pr_req_size_bytes
        + 2 * controller.config.pr_ack_size_bytes
    )
    assert summary["reservation_requests"] == 1
    assert summary["successful_reservations"] == 1
    assert summary["active_reservations"] == 1
    assert summary["control_frames_sent"] == 4
    assert summary["control_bytes_sent"] == expected_bytes
    assert float(summary["average_setup_delay"]) > 0


def test_release_propagates_and_clears_active_record() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=903)

    reservation_id = controller.schedule_reservation(packet)
    simulator.run()
    assert controller.table.get(reservation_id).status == ReservationStatus.ACTIVE

    controller.schedule_release(reservation_id)
    simulator.run()

    record = controller.table.get(reservation_id)
    assert record.status == ReservationStatus.RELEASED
    assert record.released_at is not None
    assert not controller.table.active_records

    release_frames = [
        frame
        for frame in controller.frames
        if frame.frame_type == PRMACFrameType.RELEASE
    ]
    assert len(release_frames) == 2
    assert controller.metrics.released_reservations == 1
    assert controller.trace[-1].event == "RESERVATION_RELEASED"



def test_active_reservation_expires_at_duration_boundary() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=907)

    reservation_id = controller.schedule_reservation(packet)
    simulator.run()
    record = controller.table.get(reservation_id)
    assert record.status == ReservationStatus.ACTIVE
    assert record.expires_at is not None

    expired_ids = controller.expire_reservations(now=record.expires_at)

    assert expired_ids == [reservation_id]
    assert record.status == ReservationStatus.EXPIRED
    assert controller.metrics.expired_reservations == 1
    assert not controller.table.active_records
    assert controller.trace[-1].event == "RESERVATION_EXPIRED"


def test_invalid_route_edge_is_rejected_before_events_are_scheduled() -> None:
    simulator, controller = build_controller()
    packet = make_packet(
        packet_id=904,
        route=(0, 2, 3),
    )

    try:
        controller.schedule_reservation(packet)
    except ValueError as exc:
        assert "neighbor link" in str(exc)
    else:
        raise AssertionError("A non-neighbor route edge must be rejected.")

    assert simulator.events_processed == 0
    assert not controller.table.records


def test_day09_intentionally_has_no_conflict_rejection() -> None:
    simulator, controller = build_controller()
    packet0 = make_packet(packet_id=905)
    packet1 = make_packet(packet_id=906)

    reservation0 = controller.schedule_reservation(packet0, flow_id="flow-0")
    reservation1 = controller.schedule_reservation(packet1, flow_id="flow-1")
    simulator.run()

    assert controller.table.get(reservation0).status == ReservationStatus.ACTIVE
    assert controller.table.get(reservation1).status == ReservationStatus.ACTIVE
    assert len(controller.table.active_records) == 2
    assert controller.metrics.successful_reservations == 2


def run_all_tests() -> None:
    tests = [
        test_fixed_baseline_parameters_are_frozen,
        test_k2_pr_req_and_reverse_pr_ack_activate_reservation,
        test_remaining_one_hop_truncates_effective_k,
        test_control_frames_preserve_required_fields_and_overhead,
        test_release_propagates_and_clears_active_record,
        test_active_reservation_expires_at_duration_boundary,
        test_invalid_route_edge_is_rejected_before_events_are_scheduled,
        test_day09_intentionally_has_no_conflict_rejection,
    ]

    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")

    print("\nAll Day09 Fixed-PRMAC message and reservation tests passed.")


if __name__ == "__main__":
    run_all_tests()
