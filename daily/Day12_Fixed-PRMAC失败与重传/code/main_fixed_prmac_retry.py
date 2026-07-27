"""Run the Day12 Fixed-PRMAC failure/backoff/retry demonstration."""
from __future__ import annotations

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

from packet import Packet  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_retry import FixedPRMACRetryController  # noqa: E402


def main() -> None:
    simulator = Simulator()
    adjacency = {
        0: {1},
        1: {0, 2},
        2: {1, 3},
        3: {2, 4},
        4: {3},
    }
    controller = FixedPRMACRetryController(
        simulator=simulator,
        adjacency=adjacency,
    )

    # Existing downstream reservation occupies node 2 and initially rejects
    # the candidate segment 0->1->2.
    existing_packet = Packet(
        packet_id=1500,
        source=2,
        destination=4,
        created_at=0.0,
        size_bytes=1024,
        priority=1,
        route=(2, 3, 4),
    )
    existing_id = controller.schedule_reservation(
        existing_packet,
        flow_id="day12-existing-flow",
    )
    simulator.run()

    candidate_packet = Packet(
        packet_id=1501,
        source=0,
        destination=4,
        created_at=0.0,
        size_bytes=1024,
        priority=1,
        route=(0, 1, 2, 3, 4),
    )
    retry_id = controller.schedule_reservation_with_retry(
        candidate_packet,
        flow_id="day12-retry-flow",
    )

    # The initial candidate attempt is rejected at 0.001988 s. RELEASE
    # completes at 0.002232 s; the seeded first retry starts at 0.002438 s.
    controller.schedule_release(existing_id, at=0.001900)
    simulator.run()

    retry_record = controller.retry_records[retry_id]
    if retry_record.successful_reservation_id is None:
        raise RuntimeError("Day12 demonstration expected retry success.")

    transfer_id = controller.schedule_reserved_forwarding(
        retry_record.successful_reservation_id,
        candidate_packet,
    )
    simulator.run()

    successful_reservation = controller.table.get(
        retry_record.successful_reservation_id
    )
    forwarding = controller.forwarding_records[transfer_id]

    print("\n=== Day12 Fixed-PRMAC retry and forwarding trace ===")
    for item in controller.trace:
        frame_text = f" | frame={item.frame_type}" if item.frame_type else ""
        detail_text = f" | {item.detail}" if item.detail else ""
        print(
            f"{item.time:0.9f}s | node={item.node_id} | "
            f"{item.event:<28} | packet={item.packet_id}"
            f"{frame_text}{detail_text}"
        )

    print("\n=== Retry result ===")
    print(f"retry_status                 : {retry_record.status.value}")
    print(f"total_attempts               : {retry_record.total_attempts}")
    print(f"retries_used                 : {retry_record.retries_used}")
    print(f"packet_retry_counter         : {candidate_packet.retries}")
    print(
        "attempt_statuses            : "
        + ", ".join(attempt.status.value for attempt in retry_record.attempts)
    )
    print(
        "attempt_contention_windows  : "
        + ", ".join(str(attempt.contention_window) for attempt in retry_record.attempts)
    )
    print(
        "attempt_backoff_slots       : "
        + ", ".join(
            str(
                attempt.backoff_slots_before_attempt
                if attempt.backoff_slots_before_attempt is not None
                else 0
            )
            for attempt in retry_record.attempts
        )
    )
    print(
        f"successful_reservation_status: {successful_reservation.status.value}"
    )
    print(f"retry_completion_delay       : {retry_record.completion_delay:.9f}s")

    print("\n=== Forwarding result after retry ===")
    print(f"transfer_status              : {forwarding.status.value}")
    print(f"packet_current_node          : {candidate_packet.current_node}")
    print(f"packet_current_hop_index     : {candidate_packet.current_hop_index}")
    print(f"packet_status                : {candidate_packet.status.value}")
    print(f"segment_forwarding_delay     : {forwarding.forwarding_delay:.9f}s")

    print("\n=== Metrics ===")
    summary = controller.metrics.summary(controller.table)
    for key, value in summary.items():
        print(f"{key:<38}: {value}")

    results_dir = CURRENT_DIR.parent / "results"
    trace_path = controller.export_trace_csv(
        results_dir / "fixed_prmac_retry_trace.csv"
    )
    summary_path = controller.export_retry_summary_json(
        results_dir / "fixed_prmac_retry_summary.json"
    )
    print("\nSaved:")
    print(f"- {trace_path}")
    print(f"- {summary_path}")


if __name__ == "__main__":
    main()
