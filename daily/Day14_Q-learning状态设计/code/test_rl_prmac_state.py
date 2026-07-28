"""Tests for Day14 local state design only."""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from rl_prmac_state import (
    ChannelBusyBin,
    LocalObservation,
    ReservationOutcome,
    RLState,
    StateEncoder,
    enumerate_state_space_size,
)


def make_observation(**overrides) -> LocalObservation:
    values = {
        "node_id": 2,
        "packet_id": 101,
        "flow_id": "alarm-flow-0-6",
        "observed_at": 1.0,
        "remaining_hops": 4,
        "local_queue_length": 4,
        "queue_limit": 200,
        "priority": 1,
        "last_reservation_succeeded": False,
        "recent_mean_retries": 1.5,
        "channel_busy_ratio": 0.7,
    }
    values.update(overrides)
    return LocalObservation(**values)


def test_observation_rejects_invalid_values() -> None:
    invalid_cases = [
        {"remaining_hops": 0},
        {"local_queue_length": 0},
        {"local_queue_length": 201},
        {"queue_limit": 0},
        {"recent_mean_retries": -0.1},
        {"channel_busy_ratio": -0.1},
        {"channel_busy_ratio": 1.1},
    ]
    for overrides in invalid_cases:
        try:
            make_observation(**overrides)
        except ValueError:
            continue
        raise AssertionError(f"Expected ValueError for {overrides}")


def test_remaining_hops_bins() -> None:
    encoder = StateEncoder()
    expected = {1: 0, 2: 1, 3: 2, 4: 2, 5: 3, 10: 3}
    for remaining_hops, expected_bin in expected.items():
        state = encoder.encode(make_observation(remaining_hops=remaining_hops))
        assert state.remaining_hops_bin == expected_bin


def test_queue_length_bins() -> None:
    encoder = StateEncoder()
    expected = {1: 0, 2: 1, 3: 1, 4: 2, 7: 2, 8: 3, 200: 3}
    for queue_length, expected_bin in expected.items():
        state = encoder.encode(make_observation(local_queue_length=queue_length))
        assert state.queue_length_bin == expected_bin


def test_reservation_outcome_bins() -> None:
    encoder = StateEncoder()
    assert encoder.encode(
        make_observation(last_reservation_succeeded=None)
    ).last_reservation_outcome == int(ReservationOutcome.NONE)
    assert encoder.encode(
        make_observation(last_reservation_succeeded=True)
    ).last_reservation_outcome == int(ReservationOutcome.SUCCESS)
    assert encoder.encode(
        make_observation(last_reservation_succeeded=False)
    ).last_reservation_outcome == int(ReservationOutcome.FAILURE)


def test_retry_intensity_bins() -> None:
    encoder = StateEncoder()
    expected = {0.0: 0, 0.5: 1, 1.0: 1, 1.5: 2, 2.0: 2, 2.1: 3, 7.0: 3}
    for mean_retries, expected_bin in expected.items():
        state = encoder.encode(make_observation(recent_mean_retries=mean_retries))
        assert state.retry_intensity_bin == expected_bin


def test_priority_bins() -> None:
    encoder = StateEncoder()
    assert encoder.encode(make_observation(priority=0)).priority_bin == 0
    assert encoder.encode(make_observation(priority=1)).priority_bin == 1
    assert encoder.encode(make_observation(priority=5)).priority_bin == 1


def test_channel_busy_bins_and_unknown() -> None:
    encoder = StateEncoder()
    expected = {
        None: int(ChannelBusyBin.UNKNOWN),
        0.0: int(ChannelBusyBin.LOW),
        0.24: int(ChannelBusyBin.LOW),
        0.25: int(ChannelBusyBin.MEDIUM),
        0.59: int(ChannelBusyBin.MEDIUM),
        0.60: int(ChannelBusyBin.HIGH),
        1.0: int(ChannelBusyBin.HIGH),
    }
    for busy_ratio, expected_bin in expected.items():
        state = encoder.encode(make_observation(channel_busy_ratio=busy_ratio))
        assert state.channel_busy_bin == expected_bin


def test_encoding_is_deterministic_and_hashable() -> None:
    encoder = StateEncoder()
    observation = make_observation()
    state_a = encoder.encode(observation)
    state_b = encoder.encode(observation)
    assert state_a == state_b
    assert hash(state_a) == hash(state_b)
    assert isinstance(state_a.as_tuple(), tuple)


def test_state_space_size_is_bounded() -> None:
    assert enumerate_state_space_size() == 1536


def test_observation_contains_only_declared_local_fields() -> None:
    names = {field.name for field in fields(LocalObservation)}
    expected = {
        "node_id",
        "packet_id",
        "flow_id",
        "observed_at",
        "remaining_hops",
        "local_queue_length",
        "queue_limit",
        "priority",
        "last_reservation_succeeded",
        "recent_mean_retries",
        "channel_busy_ratio",
    }
    forbidden = {
        "global_queue_length",
        "global_channel_state",
        "all_node_states",
        "future_delay",
        "end_to_end_future_information",
        "central_controller",
    }
    assert names == expected
    assert names.isdisjoint(forbidden)


def test_state_tuple_order_is_stable() -> None:
    state = RLState(0, 1, 2, 3, 1, 0)
    assert state.as_tuple() == (0, 1, 2, 3, 1, 0)


TESTS = [
    test_observation_rejects_invalid_values,
    test_remaining_hops_bins,
    test_queue_length_bins,
    test_reservation_outcome_bins,
    test_retry_intensity_bins,
    test_priority_bins,
    test_channel_busy_bins_and_unknown,
    test_encoding_is_deterministic_and_hashable,
    test_state_space_size_is_bounded,
    test_observation_contains_only_declared_local_fields,
    test_state_tuple_order_is_stable,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"[PASS] {test.__name__}")
    print()
    print("All Day14 Q-learning state-design tests passed.")
