"""Tests for Day10 Fixed-PRMAC conflict detection and PR_NACK."""
from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"

# Force a deterministic import order. When a Python script is executed directly,
# CURRENT_DIR is already present in sys.path. Merely skipping existing entries
# would allow DAY09_CODE to be inserted ahead of Day10 and would load Day09's
# ReservationStatus (which has no REJECTED state).
_import_paths = [CURRENT_DIR, DAY09_CODE, DAY03_CODE]
for path in _import_paths:
    path_text = str(path)
    while path_text in sys.path:
        sys.path.remove(path_text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from packet import Packet  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_messages import PRMACFrameType, ReservationStatus  # noqa: E402
from fixed_prmac_conflict import FixedPRMACConflictController  # noqa: E402


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
    controller = FixedPRMACConflictController(
        simulator=simulator,
        adjacency=adjacency,
    )
    return simulator, controller


def make_packet(
    *,
    packet_id: int,
    route: tuple[int, ...],
    current_hop_index: int = 0,
    priority: int = 1,
) -> Packet:
    return Packet(
        packet_id=packet_id,
        source=route[0],
        destination=route[-1],
        created_at=0.0,
        priority=priority,
        route=route,
        current_hop_index=current_hop_index,
    )


def activate(
    simulator: Simulator,
    controller: FixedPRMACConflictController,
    packet: Packet,
    *,
    flow_id: str,
) -> str:
    reservation_id = controller.schedule_reservation(packet, flow_id=flow_id)
    simulator.run()
    assert controller.table.get(reservation_id).status == ReservationStatus.ACTIVE
    return reservation_id


def test_disjoint_overlapping_time_reservations_can_coexist() -> None:
    simulator, controller = build_controller()
    first_id = activate(
        simulator,
        controller,
        make_packet(packet_id=1000, route=(0, 1, 2)),
        flow_id="flow-left",
    )
    second_id = activate(
        simulator,
        controller,
        make_packet(packet_id=1001, route=(4, 5, 6)),
        flow_id="flow-right",
    )

    assert controller.table.get(first_id).status == ReservationStatus.ACTIVE
    assert controller.table.get(second_id).status == ReservationStatus.ACTIVE
    assert len(controller.table.active_records) == 2
    assert controller.metrics.rejected_reservations == 0


def test_same_link_overlap_is_rejected() -> None:
    simulator, controller = build_controller()
    existing_id = activate(
        simulator,
        controller,
        make_packet(packet_id=1010, route=(0, 1, 2)),
        flow_id="flow-existing",
    )
    rejected_id = controller.schedule_reservation(
        make_packet(packet_id=1011, route=(0, 1, 2)),
        flow_id="flow-overlap",
    )
    simulator.run()

    existing = controller.table.get(existing_id)
    rejected = controller.table.get(rejected_id)
    assert existing.status == ReservationStatus.ACTIVE
    assert rejected.status == ReservationStatus.REJECTED
    assert "LINK_CONFLICT" in rejected.failure_reason
    assert controller.metrics.link_conflicts == 1


def test_shared_node_overlap_is_rejected_without_same_link() -> None:
    simulator, controller = build_controller()
    activate(
        simulator,
        controller,
        make_packet(packet_id=1020, route=(0, 1, 2)),
        flow_id="flow-existing-node",
    )
    rejected_id = controller.schedule_reservation(
        make_packet(packet_id=1021, route=(3, 1, 4)),
        flow_id="flow-shared-node",
    )
    simulator.run()

    rejected = controller.table.get(rejected_id)
    assert rejected.status == ReservationStatus.REJECTED
    assert "NODE_CONFLICT" in rejected.failure_reason
    assert "node-1" in rejected.failure_reason
    assert controller.metrics.node_conflicts == 1


def test_non_overlapping_time_window_is_accepted_and_old_record_expires() -> None:
    simulator, controller = build_controller()
    existing_id = activate(
        simulator,
        controller,
        make_packet(packet_id=1030, route=(0, 1, 2)),
        flow_id="flow-time-old",
    )
    existing = controller.table.get(existing_id)
    assert existing.expires_at is not None

    new_id = controller.schedule_reservation(
        make_packet(packet_id=1031, route=(0, 1, 2)),
        flow_id="flow-time-new",
        at=existing.expires_at,
    )
    simulator.run()

    assert existing.status == ReservationStatus.EXPIRED
    assert controller.table.get(new_id).status == ReservationStatus.ACTIVE
    assert controller.metrics.expired_reservations == 1


def test_pr_nack_returns_along_reverse_partial_path() -> None:
    simulator, controller = build_controller(log_enabled=True)
    activate(
        simulator,
        controller,
        make_packet(packet_id=1040, route=(2, 3, 4)),
        flow_id="flow-downstream-existing",
    )
    rejected_id = controller.schedule_reservation(
        make_packet(packet_id=1041, route=(0, 1, 2)),
        flow_id="flow-two-hop-nack",
    )
    simulator.run()

    rejected = controller.table.get(rejected_id)
    assert rejected.status == ReservationStatus.REJECTED

    rejected_trace = [
        item for item in controller.trace if item.reservation_id == rejected_id
    ]
    nack_tx = [item for item in rejected_trace if item.event == "PR_NACK_TX"]
    nack_rx = [item for item in rejected_trace if item.event == "PR_NACK_RX"]
    assert len(nack_tx) == 2
    assert len(nack_rx) == 2
    assert [item.node_id for item in nack_tx] == [2, 1]
    assert [item.node_id for item in nack_rx] == [1, 0]
    assert rejected_trace[-1].event == "RESERVATION_REJECTED"

    nack_frames = [
        frame
        for frame in controller.frames
        if frame.packet_id == 1041
        and frame.frame_type == PRMACFrameType.PR_NACK
    ]
    assert len(nack_frames) == 2
    assert all(frame.reason for frame in nack_frames)
    assert controller.metrics.pr_nack_frames_sent == 2
    assert "GENERIC" not in "\n".join(simulator.log_records)


def test_rejected_request_does_not_pollute_existing_active_reservation() -> None:
    simulator, controller = build_controller()
    existing_id = activate(
        simulator,
        controller,
        make_packet(packet_id=1050, route=(0, 1, 2)),
        flow_id="flow-clean-existing",
    )
    existing_before = controller.table.get(existing_id)
    activated_at_before = existing_before.activated_at
    expires_at_before = existing_before.expires_at

    rejected_id = controller.schedule_reservation(
        make_packet(packet_id=1051, route=(0, 1, 2)),
        flow_id="flow-clean-rejected",
    )
    simulator.run()

    existing_after = controller.table.get(existing_id)
    rejected = controller.table.get(rejected_id)
    assert existing_after.status == ReservationStatus.ACTIVE
    assert existing_after.activated_at == activated_at_before
    assert existing_after.expires_at == expires_at_before
    assert rejected.status == ReservationStatus.REJECTED
    assert rejected not in controller.table.active_records
    assert len(controller.table.active_records) == 1


def test_release_frees_resources_for_new_reservation() -> None:
    simulator, controller = build_controller()
    existing_id = activate(
        simulator,
        controller,
        make_packet(packet_id=1060, route=(0, 1, 2)),
        flow_id="flow-release-old",
    )
    controller.schedule_release(existing_id)
    simulator.run()
    assert controller.table.get(existing_id).status == ReservationStatus.RELEASED

    new_id = activate(
        simulator,
        controller,
        make_packet(packet_id=1061, route=(0, 1, 2)),
        flow_id="flow-release-new",
    )
    assert controller.table.get(new_id).status == ReservationStatus.ACTIVE


def test_reverse_direction_uses_same_physical_link_resource() -> None:
    simulator, controller = build_controller()
    activate(
        simulator,
        controller,
        make_packet(packet_id=1070, route=(0, 1, 2)),
        flow_id="flow-forward",
    )
    rejected_id = controller.schedule_reservation(
        make_packet(packet_id=1071, route=(2, 1, 0)),
        flow_id="flow-reverse",
    )
    simulator.run()

    rejected = controller.table.get(rejected_id)
    assert rejected.status == ReservationStatus.REJECTED
    assert "LINK_CONFLICT" in rejected.failure_reason


def run_all_tests() -> None:
    tests = [
        test_disjoint_overlapping_time_reservations_can_coexist,
        test_same_link_overlap_is_rejected,
        test_shared_node_overlap_is_rejected_without_same_link,
        test_non_overlapping_time_window_is_accepted_and_old_record_expires,
        test_pr_nack_returns_along_reverse_partial_path,
        test_rejected_request_does_not_pollute_existing_active_reservation,
        test_release_frees_resources_for_new_reservation,
        test_reverse_direction_uses_same_physical_link_resource,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("\nAll Day10 Fixed-PRMAC conflict tests passed.")


if __name__ == "__main__":
    run_all_tests()
