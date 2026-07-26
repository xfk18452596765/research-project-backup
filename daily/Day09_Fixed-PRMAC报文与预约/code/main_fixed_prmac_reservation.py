"""Run the Day09 Fixed-PRMAC successful reservation demonstration."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

for path in (CURRENT_DIR, DAY03_CODE):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from packet import Packet  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402

from fixed_prmac_reservation import FixedPRMACReservationController


def main() -> None:
    simulator = Simulator()
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
    packet = Packet(
        packet_id=900,
        source=0,
        destination=4,
        created_at=0.0,
        priority=1,
        route=(0, 1, 2, 3, 4),
    )

    reservation_id = controller.schedule_reservation(
        packet,
        flow_id="demo-flow",
    )
    simulator.run()

    record = controller.table.get(reservation_id)

    print("\n=== Fixed-PRMAC reservation trace ===")
    for item in controller.trace:
        frame_text = f" | frame={item.frame_type}" if item.frame_type else ""
        detail_text = f" | {item.detail}" if item.detail else ""
        print(
            f"{item.time:0.9f}s | node={item.node_id} | "
            f"{item.event:<22} | packet={item.packet_id}"
            f"{frame_text}{detail_text}"
        )

    print("\n=== Reservation result ===")
    print(f"reservation_id       : {record.reservation_id}")
    print(f"status               : {record.status.value}")
    print(f"requested_k          : {record.requested_hops}")
    print(f"effective_k          : {record.effective_hops}")
    print(
        "reserved_links       : "
        + ", ".join(
            f"{link.sender}->{link.receiver}"
            for link in record.reserved_links
        )
    )
    print(f"initiator            : {record.initiator}")
    print(f"endpoint             : {record.endpoint}")
    print(f"activated_at         : {record.activated_at:.9f}s")
    print(f"expires_at           : {record.expires_at:.9f}s")

    summary = controller.metrics.summary(controller.table)
    for key, value in summary.items():
        print(f"{key:<21}: {value}")

    results_dir = CURRENT_DIR.parent / "results"
    trace_path = controller.export_trace_csv(
        results_dir / "fixed_prmac_reservation_trace.csv"
    )
    summary_path = controller.export_summary_json(
        results_dir / "fixed_prmac_reservation_summary.json"
    )
    print("\nSaved:")
    print(f"- {trace_path}")
    print(f"- {summary_path}")


if __name__ == "__main__":
    main()
