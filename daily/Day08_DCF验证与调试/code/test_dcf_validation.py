"""Automated tests for Day08 DCF validation and debugging."""

from __future__ import annotations

import math
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from dcf_validation import (  # noqa: E402
    run_converging_collision_smoke,
    run_periodic_chain_case,
)
from packet import PacketStatus  # type: ignore  # noqa: E402


def _packet_delays(case) -> tuple[float, ...]:
    return tuple(
        float(packet.end_to_end_delay)
        for packet in case.packets
        if packet.end_to_end_delay is not None
    )


def test_schedule_at_event_names_are_not_generic() -> None:
    case, _ = run_periodic_chain_case(
        2,
        packet_count=2,
        interarrival_time=0.020,
        seed=7,
        log_enabled=True,
    )

    assert case.simulator.log_records
    assert all("GENERIC" not in record for record in case.simulator.log_records)

    log_text = "\n".join(case.simulator.log_records)
    assert "PACKET_ARRIVAL" in log_text
    assert "TX_SLOT_RESOLVE" in log_text
    assert "FORWARD_ARRIVAL" in log_text


def test_same_seed_is_reproducible() -> None:
    case_a, row_a = run_periodic_chain_case(
        4,
        packet_count=6,
        interarrival_time=0.012,
        seed=17,
    )
    case_b, row_b = run_periodic_chain_case(
        4,
        packet_count=6,
        interarrival_time=0.012,
        seed=17,
    )

    assert _packet_delays(case_a) == _packet_delays(case_b)
    for key in (
        "delivery_ratio",
        "average_end_to_end_delay",
        "p95_end_to_end_delay",
        "shared_collision_events",
        "retransmissions",
        "average_queue_delay",
        "average_access_delay",
    ):
        assert row_a[key] == row_b[key]


def test_different_seed_changes_randomized_result() -> None:
    case_a, _ = run_periodic_chain_case(
        4,
        packet_count=6,
        interarrival_time=0.012,
        seed=7,
    )
    case_b, _ = run_periodic_chain_case(
        4,
        packet_count=6,
        interarrival_time=0.012,
        seed=27,
    )

    assert _packet_delays(case_a) != _packet_delays(case_b)


def test_delay_decomposition_and_queue_boundary() -> None:
    case, row = run_periodic_chain_case(
        4,
        packet_count=6,
        interarrival_time=0.001,
        seed=7,
    )

    assert case.metrics.hop_records
    assert row["maximum_decomposition_error"] < 1e-12
    assert any(record.queue_delay > 0 for record in case.metrics.hop_records)

    for record in case.metrics.hop_records:
        assert record.queue_delay >= 0
        assert record.access_delay >= 0
        assert record.tx_ack_delay >= 0
        assert math.isclose(
            record.hop_delay,
            record.queue_delay + record.access_delay + record.tx_ack_delay,
            abs_tol=1e-12,
        )


def test_high_load_increases_queueing_delay() -> None:
    _, low = run_periodic_chain_case(
        4,
        packet_count=8,
        interarrival_time=0.050,
        seed=17,
    )
    _, high = run_periodic_chain_case(
        4,
        packet_count=8,
        interarrival_time=0.008,
        seed=17,
    )

    assert float(high["average_queue_delay"]) > float(low["average_queue_delay"])
    assert float(high["average_end_to_end_delay"]) >= float(
        low["average_end_to_end_delay"]
    )


def test_converging_collision_smoke_preserves_day06_and_day07() -> None:
    context, row = run_converging_collision_smoke(log_enabled=True)
    packets = context["packets"]

    assert all(packet.status == PacketStatus.DELIVERED for packet in packets)
    assert row["created_packets"] == 2
    assert row["delivered_packets"] == 2
    assert row["successful_hops"] == 4
    assert row["shared_collision_events"] == 1
    assert row["collided_packet_attempts"] == 2
    assert row["retransmissions"] == 2
    assert row["backoff_freezes"] >= 1
    assert row["queues_empty"] == 1
    assert row["channel_idle"] == 1
    assert float(row["maximum_decomposition_error"]) < 1e-12
    assert all(
        "GENERIC" not in record
        for record in context["simulator"].log_records
    )


def run_all_tests() -> None:
    tests = [
        test_schedule_at_event_names_are_not_generic,
        test_same_seed_is_reproducible,
        test_different_seed_changes_randomized_result,
        test_delay_decomposition_and_queue_boundary,
        test_high_load_increases_queueing_delay,
        test_converging_collision_smoke_preserves_day06_and_day07,
    ]

    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")

    print("\nAll Day08 DCF validation and debugging tests passed.")


if __name__ == "__main__":
    run_all_tests()
