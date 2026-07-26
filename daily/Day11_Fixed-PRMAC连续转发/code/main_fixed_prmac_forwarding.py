"""Run the Day11 Fixed-PRMAC reserved-segment forwarding demonstration."""
from __future__ import annotations

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

from packet import Packet  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_forwarding import FixedPRMACForwardingController  # noqa: E402


def main() -> None:
    simulator = Simulator()
    adjacency = {
        0: {1},
        1: {0, 2},
        2: {1, 3},
        3: {2, 4},
        4: {3},
    }
    controller = FixedPRMACForwardingController(
        simulator=simulator,
        adjacency=adjacency,
    )
    packet = Packet(
        packet_id=1300,
        source=0,
        destination=4,
        created_at=0.0,
        size_bytes=1024,
        priority=1,
        route=(0, 1, 2, 3, 4),
    )

    reservation_id = controller.schedule_reservation(
        packet,
        flow_id="day11-demo-flow",
    )
    simulator.run()

    transfer_id = controller.schedule_reserved_forwarding(
        reservation_id,
        packet,
    )
    simulator.run()

    reservation = controller.table.get(reservation_id)
    forwarding = controller.forwarding_records[transfer_id]

    print("\n=== Day11 Fixed-PRMAC forwarding trace ===")
    for item in controller.trace:
        frame_text = f" | frame={item.frame_type}" if item.frame_type else ""
        detail_text = f" | {item.detail}" if item.detail else ""
        print(
            f"{item.time:0.9f}s | node={item.node_id} | "
            f"{item.event:<26} | packet={item.packet_id}"
            f"{frame_text}{detail_text}"
        )

    print("\n=== Forwarding result ===")
    print(f"reservation_status       : {reservation.status.value}")
    print(f"transfer_status          : {forwarding.status.value}")
    print(f"requested_k              : {reservation.requested_hops}")
    print(f"effective_k              : {reservation.effective_hops}")
    print(f"packet_current_node      : {packet.current_node}")
    print(f"packet_current_hop_index : {packet.current_hop_index}")
    print(f"packet_status            : {packet.status.value}")
    print(f"segment_started_at       : {forwarding.started_at:.9f}s")
    print(f"segment_completed_at     : {forwarding.completed_at:.9f}s")
    print(f"segment_forwarding_delay : {forwarding.forwarding_delay:.9f}s")

    summary = controller.metrics.summary(controller.table)
    for key, value in summary.items():
        print(f"{key:<26}: {value}")

    results_dir = CURRENT_DIR.parent / "results"
    trace_path = controller.export_trace_csv(
        results_dir / "fixed_prmac_forwarding_trace.csv"
    )
    summary_path = controller.export_forwarding_summary_json(
        results_dir / "fixed_prmac_forwarding_summary.json"
    )
    print("\nSaved:")
    print(f"- {trace_path}")
    print(f"- {summary_path}")


if __name__ == "__main__":
    main()
