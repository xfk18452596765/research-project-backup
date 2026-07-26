"""Run the Day10 Fixed-PRMAC conflict and PR_NACK demonstration."""
from __future__ import annotations

import json
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
from fixed_prmac_conflict import FixedPRMACConflictController  # noqa: E402


def make_packet(packet_id: int, route: tuple[int, ...]) -> Packet:
    return Packet(
        packet_id=packet_id,
        source=route[0],
        destination=route[-1],
        created_at=0.0,
        priority=1,
        route=route,
    )


def main() -> None:
    simulator = Simulator()
    adjacency = {
        0: {1},
        1: {0, 2},
        2: {1, 3},
        3: {2, 4},
        4: {3},
    }
    controller = FixedPRMACConflictController(
        simulator=simulator,
        adjacency=adjacency,
    )

    existing_id = controller.schedule_reservation(
        make_packet(1100, (2, 3, 4)),
        flow_id="existing-flow",
    )
    simulator.run()

    rejected_id = controller.schedule_reservation(
        make_packet(1101, (0, 1, 2)),
        flow_id="conflicting-flow",
    )
    simulator.run()

    print("\n=== Day10 reservation conflict trace ===")
    for item in controller.trace:
        frame_text = f" | frame={item.frame_type}" if item.frame_type else ""
        detail_text = f" | {item.detail}" if item.detail else ""
        print(
            f"{item.time:0.9f}s | node={item.node_id} | "
            f"{item.event:<24} | packet={item.packet_id}"
            f"{frame_text}{detail_text}"
        )

    existing = controller.table.get(existing_id)
    rejected = controller.table.get(rejected_id)
    print("\n=== Reservation result ===")
    print(f"existing_status       : {existing.status.value}")
    print(f"rejected_status       : {rejected.status.value}")
    print(f"failure_reason        : {rejected.failure_reason}")

    summary = controller.metrics.summary(controller.table)
    for key, value in summary.items():
        print(f"{key:<23}: {value}")

    results_dir = CURRENT_DIR.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    trace_path = controller.export_trace_csv(
        results_dir / "fixed_prmac_conflict_trace.csv"
    )
    summary_path = results_dir / "fixed_prmac_conflict_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "metrics": summary,
                "reservations": controller.conflict_snapshot(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("\nSaved:")
    print(f"- {trace_path}")
    print(f"- {summary_path}")


if __name__ == "__main__":
    main()
