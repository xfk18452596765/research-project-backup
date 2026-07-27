"""Tests for Day12 Fixed-PRMAC reservation failure, backoff, and retry."""
from __future__ import annotations

import math
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY11_CODE = DAILY_DIR / "Day11_Fixed-PRMAC连续转发" / "code"
DAY10_CODE = DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

_import_paths = [CURRENT_DIR, DAY11_CODE, DAY10_CODE, DAY09_CODE, DAY03_CODE]
for path in _import_paths:
    path_text = str(path)
    while path_text in sys.path:
        sys.path.remove(path_text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_messages import ReservationStatus  # noqa: E402
from fixed_prmac_forwarding import SegmentForwardingStatus  # type: ignore  # noqa: E402
from fixed_prmac_retry import (  # noqa: E402
    Day12FixedPRMACConfig,
    FixedPRMACRetryController,
    ReservationRetryStatus,
)


ADJACENCY = {
    0: {1},
    1: {0, 2, 4},
    2: {1, 3},
    3: {1, 2, 4},
    4: {3, 5},
    5: {4, 6},
    6: {5},
}


def build_controller(
    *,
    config: Day12FixedPRMACConfig | None = None,
    log_enabled: bool = False,
):
    simulator = Simulator()
    simulator.log_enabled = log_enabled
    controller = FixedPRMACRetryController(
        simulator=simulator,
        config=config,
        adjacency=ADJACENCY,
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


def activate_existing(
    simulator: Simulator,
    controller: FixedPRMACRetryController,
    *,
    packet_id: int,
    route: tuple[int, ...],
    flow_id: str,
) -> str:
    packet = make_packet(packet_id=packet_id, route=route)
    reservation_id = controller.schedule_reservation(packet, flow_id=flow_id)
    simulator.run()
    assert controller.table.get(reservation_id).status == ReservationStatus.ACTIVE
    return reservation_id


def run_conflict_then_release(
    *,
    packet_id_base: int,
    config: Day12FixedPRMACConfig | None = None,
    candidate_route: tuple[int, ...] = (0, 1, 2),
):
    simulator, controller = build_controller(config=config)
    existing_id = activate_existing(
        simulator,
        controller,
        packet_id=packet_id_base,
        route=(2, 3, 4),
        flow_id=f"existing-{packet_id_base}",
    )
    candidate = make_packet(
        packet_id=packet_id_base + 1,
        route=candidate_route,
    )
    retry_id = controller.schedule_reservation_with_retry(
        candidate,
        flow_id=f"candidate-{packet_id_base}",
    )
    # Initial candidate is rejected at 0.001988 s. The existing reservation
    # finishes RELEASE at 0.002232 s, before the seeded first retry at 0.002438 s.
    controller.schedule_release(existing_id, at=0.001900)
    simulator.run()
    return simulator, controller, existing_id, candidate, retry_id


def run_persistent_conflict(
    *,
    packet_id_base: int,
    config: Day12FixedPRMACConfig,
):
    simulator, controller = build_controller(config=config)
    existing_id = activate_existing(
        simulator,
        controller,
        packet_id=packet_id_base,
        route=(2, 3, 4),
        flow_id=f"persistent-existing-{packet_id_base}",
    )
    candidate = make_packet(
        packet_id=packet_id_base + 1,
        route=(0, 1, 2),
    )
    retry_id = controller.schedule_reservation_with_retry(
        candidate,
        flow_id=f"persistent-candidate-{packet_id_base}",
    )
    simulator.run()
    return simulator, controller, existing_id, candidate, retry_id


def test_day12_retry_defaults_match_existing_dcf_baseline() -> None:
    config = Day12FixedPRMACConfig()
    assert config.fixed_cw_min == 15
    assert config.slot_time == 20e-6
    assert config.difs_time == 50e-6
    assert config.cw_max == 1023
    assert config.retry_limit == 7
    assert config.random_seed == 7
    assert config.contention_window_for_retry(1) == 31
    assert config.contention_window_for_retry(2) == 63
    assert config.contention_window_for_retry(6) == 1023
    assert config.contention_window_for_retry(7) == 1023


def test_no_conflict_succeeds_on_first_attempt_without_backoff() -> None:
    simulator, controller = build_controller()
    packet = make_packet(packet_id=1400, route=(0, 1, 2))
    retry_id = controller.schedule_reservation_with_retry(
        packet,
        flow_id="first-attempt-success",
    )
    simulator.run()

    retry_record = controller.retry_records[retry_id]
    assert retry_record.status == ReservationRetryStatus.SUCCEEDED
    assert retry_record.total_attempts == 1
    assert retry_record.retries_used == 0
    assert packet.retries == 0
    assert retry_record.successful_reservation_id is not None
    assert (
        controller.table.get(retry_record.successful_reservation_id).status
        == ReservationStatus.ACTIVE
    )
    assert controller.metrics.first_attempt_successes == 1
    assert controller.metrics.retry_successes == 0
    assert controller.metrics.reservation_retries_scheduled == 0
    assert controller.metrics.total_retry_backoff_slots == 0


def test_pr_nack_triggers_seeded_beb_and_first_retry_succeeds_after_release() -> None:
    simulator, controller, existing_id, packet, retry_id = run_conflict_then_release(
        packet_id_base=1410,
    )
    retry_record = controller.retry_records[retry_id]
    assert retry_record.status == ReservationRetryStatus.SUCCEEDED
    assert retry_record.total_attempts == 2
    assert retry_record.retries_used == 1
    assert packet.retries == 1
    assert controller.table.get(existing_id).status == ReservationStatus.RELEASED

    first, second = retry_record.attempts
    assert first.status == ReservationStatus.REJECTED
    assert second.status == ReservationStatus.ACTIVE
    assert first.contention_window == 15
    assert second.contention_window == 31
    assert second.backoff_slots_before_attempt == 20
    assert math.isclose(
        second.backoff_delay_before_attempt,
        50e-6 + 20 * 20e-6,
        abs_tol=1e-15,
    )
    assert first.completed_at is not None
    assert math.isclose(
        second.scheduled_at - first.completed_at,
        second.backoff_delay_before_attempt,
        abs_tol=1e-15,
    )
    assert controller.metrics.retry_successes == 1
    assert controller.metrics.retry_exhausted_failures == 0
    assert controller.metrics.reservation_retries_scheduled == 1


def test_each_retry_uses_a_fresh_reservation_id_and_preserves_history() -> None:
    _, controller, _, _, retry_id = run_conflict_then_release(
        packet_id_base=1420,
    )
    retry_record = controller.retry_records[retry_id]
    ids = [attempt.reservation_id for attempt in retry_record.attempts]
    assert len(ids) == len(set(ids)) == 2
    assert controller.table.get(ids[0]).status == ReservationStatus.REJECTED
    assert controller.table.get(ids[1]).status == ReservationStatus.ACTIVE
    assert controller.table.get(ids[0]).failure_reason
    assert retry_record.successful_reservation_id == ids[1]


def test_retry_event_order_is_rejection_then_backoff_then_new_attempt() -> None:
    _, controller, _, packet, retry_id = run_conflict_then_release(
        packet_id_base=1430,
    )
    retry_record = controller.retry_records[retry_id]
    reservation_ids = {
        attempt.reservation_id for attempt in retry_record.attempts
    }
    trace = [
        item
        for item in controller.trace
        if item.packet_id == packet.packet_id
        and (
            item.reservation_id in reservation_ids
            or item.event.startswith("RETRY_")
        )
    ]
    events = [item.event for item in trace]
    rejected_index = events.index("RESERVATION_REJECTED")
    backoff_index = events.index("RETRY_BACKOFF_START")
    second_attempt_indices = [
        index
        for index, item in enumerate(trace)
        if item.event == "RETRY_ATTEMPT_START"
        and "attempt=2" in item.detail
    ]
    assert second_attempt_indices
    assert rejected_index < backoff_index < second_attempt_indices[0]
    assert events[-1] == "RETRY_SEQUENCE_SUCCEEDED"


def test_persistent_conflict_exhausts_limit_and_marks_final_attempt_failed() -> None:
    config = Day12FixedPRMACConfig(retry_limit=2, random_seed=7)
    _, controller, existing_id, packet, retry_id = run_persistent_conflict(
        packet_id_base=1440,
        config=config,
    )
    retry_record = controller.retry_records[retry_id]
    assert controller.table.get(existing_id).status == ReservationStatus.ACTIVE
    assert retry_record.status == ReservationRetryStatus.FAILED
    assert retry_record.total_attempts == 3
    assert retry_record.retries_used == 2
    assert packet.retries == 2
    assert packet.status == PacketStatus.DROPPED
    assert [attempt.status for attempt in retry_record.attempts] == [
        ReservationStatus.REJECTED,
        ReservationStatus.REJECTED,
        ReservationStatus.FAILED,
    ]
    final_record = controller.table.get(
        retry_record.attempts[-1].reservation_id
    )
    assert final_record.status == ReservationStatus.FAILED
    assert final_record.failed_at is not None
    assert "retry_limit_exhausted=2" in final_record.failure_reason
    assert controller.metrics.retry_exhausted_failures == 1
    assert controller.metrics.reservation_retries_scheduled == 2
    assert controller.metrics.rejected_reservations == 3


def test_binary_exponential_window_growth_is_capped() -> None:
    config = Day12FixedPRMACConfig(
        retry_limit=3,
        cw_max=31,
        random_seed=7,
    )
    _, controller, _, _, retry_id = run_persistent_conflict(
        packet_id_base=1450,
        config=config,
    )
    retry_record = controller.retry_records[retry_id]
    assert retry_record.status == ReservationRetryStatus.FAILED
    assert [attempt.contention_window for attempt in retry_record.attempts] == [
        15,
        31,
        31,
        31,
    ]


def _backoff_slots_for_seed(seed: int) -> tuple[int, ...]:
    config = Day12FixedPRMACConfig(retry_limit=2, random_seed=seed)
    _, controller, _, _, retry_id = run_persistent_conflict(
        packet_id_base=1500 + seed,
        config=config,
    )
    return tuple(
        attempt.backoff_slots_before_attempt
        for attempt in controller.retry_records[retry_id].attempts[1:]
        if attempt.backoff_slots_before_attempt is not None
    )


def test_retry_random_seed_is_reproducible() -> None:
    first = _backoff_slots_for_seed(7)
    second = _backoff_slots_for_seed(7)
    different = _backoff_slots_for_seed(11)
    assert first == second == (20, 19)
    assert different != first


def test_plain_day10_rejection_does_not_enable_automatic_retry() -> None:
    simulator, controller = build_controller()
    activate_existing(
        simulator,
        controller,
        packet_id=1460,
        route=(2, 3, 4),
        flow_id="plain-existing",
    )
    packet = make_packet(packet_id=1461, route=(0, 1, 2))
    reservation_id = controller.schedule_reservation(
        packet,
        flow_id="plain-untracked",
    )
    simulator.run()

    assert controller.table.get(reservation_id).status == ReservationStatus.REJECTED
    assert controller.retry_records == {}
    assert controller.metrics.retry_sequences_started == 0
    assert controller.metrics.reservation_retries_scheduled == 0


def test_successful_retry_can_use_inherited_day11_data_h_ack_forwarding() -> None:
    simulator, controller, _, packet, retry_id = run_conflict_then_release(
        packet_id_base=1470,
        candidate_route=(0, 1, 2, 3, 4),
    )
    retry_record = controller.retry_records[retry_id]
    assert retry_record.successful_reservation_id is not None

    transfer_id = controller.schedule_reserved_forwarding(
        retry_record.successful_reservation_id,
        packet,
    )
    simulator.run()
    forwarding = controller.forwarding_records[transfer_id]
    assert forwarding.status == SegmentForwardingStatus.COMPLETED
    assert packet.current_node == 2
    assert packet.current_hop_index == 2
    assert packet.status == PacketStatus.FORWARDED
    assert controller.metrics.data_frames_sent == 2
    assert controller.metrics.h_ack_frames_sent == 2
    assert controller.metrics.completed_segments == 1


def test_retry_metrics_include_all_attempts_backoff_and_control_overhead() -> None:
    _, controller, _, _, retry_id = run_conflict_then_release(
        packet_id_base=1480,
    )
    retry_record = controller.retry_records[retry_id]
    summary = controller.metrics.summary(controller.table)
    assert retry_record.status == ReservationRetryStatus.SUCCEEDED
    assert summary["retry_sequences_started"] == 1
    assert summary["retry_attempts_scheduled"] == 2
    assert summary["reservation_retries_scheduled"] == 1
    assert summary["retry_successes"] == 1
    assert summary["retry_exhausted_failures"] == 0
    assert summary["total_retry_backoff_slots"] == 20
    assert math.isclose(
        float(summary["total_retry_backoff_delay"]),
        0.00045,
        abs_tol=1e-15,
    )
    assert math.isclose(
        float(summary["retry_sequence_success_rate"]),
        1.0,
        abs_tol=1e-15,
    )
    # Existing success: 4 frames. Candidate rejected attempt: 4 frames.
    # Candidate successful retry: 4 frames. Existing RELEASE: 2 frames.
    assert summary["control_frames_sent"] == 14
    assert summary["control_bytes_sent"] == 400


def run_all_tests() -> None:
    tests = [
        test_day12_retry_defaults_match_existing_dcf_baseline,
        test_no_conflict_succeeds_on_first_attempt_without_backoff,
        test_pr_nack_triggers_seeded_beb_and_first_retry_succeeds_after_release,
        test_each_retry_uses_a_fresh_reservation_id_and_preserves_history,
        test_retry_event_order_is_rejection_then_backoff_then_new_attempt,
        test_persistent_conflict_exhausts_limit_and_marks_final_attempt_failed,
        test_binary_exponential_window_growth_is_capped,
        test_retry_random_seed_is_reproducible,
        test_plain_day10_rejection_does_not_enable_automatic_retry,
        test_successful_retry_can_use_inherited_day11_data_h_ack_forwarding,
        test_retry_metrics_include_all_attempts_backoff_and_control_overhead,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print("\nAll Day12 Fixed-PRMAC failure-and-retry tests passed.")


if __name__ == "__main__":
    run_all_tests()
