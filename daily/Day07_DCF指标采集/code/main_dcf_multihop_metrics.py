"""Run Day07 DCF hop-scaling and metric-collection experiments."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
DAY05_CODE = DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
DAY06_CODE = DAILY_DIR / "Day06_DCF碰撞与重传" / "code"
for path in (CURRENT_DIR, DAY03_CODE, DAY04_CODE, DAY05_CODE, DAY06_CODE):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from node import Node  # type: ignore  # noqa: E402
from packet import Packet  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from dcf_config import DCFConfig  # type: ignore  # noqa: E402
from dcf_multihop_metrics import (  # noqa: E402
    CollisionChannel,
    DCFContentionCoordinator,
    DCFMetricsCollector,
    DCFMultiHopMac,
    DCFMultiHopNetwork,
    SequenceRandom,
)


def build_chain_case(
    hop_count: int,
    *,
    backoff_slots: int = 10,
    packet_id: int = 700,
):
    if hop_count <= 0:
        raise ValueError("hop_count must be positive.")

    simulator = Simulator()
    channel = CollisionChannel()
    config = DCFConfig()
    metrics = DCFMetricsCollector(slot_time=config.slot_time)
    coordinator = DCFContentionCoordinator(simulator, channel, config)
    network = DCFMultiHopNetwork(simulator=simulator, metrics=metrics)

    nodes = [Node(node_id=index) for index in range(hop_count + 1)]
    macs = []
    for sender in range(hop_count):
        nodes[sender].neighbors.add(sender + 1)
        mac = DCFMultiHopMac(
            simulator=simulator,
            node=nodes[sender],
            channel=channel,
            metrics=metrics,
            config=config,
            rng=SequenceRandom([backoff_slots]),
            coordinator=coordinator,
            network=network,
        )
        macs.append(mac)

    packet = Packet(
        packet_id=packet_id,
        source=0,
        destination=hop_count,
        created_at=0.0,
        size_bytes=1024,
        route=tuple(range(hop_count + 1)),
    )
    return simulator, channel, config, metrics, coordinator, network, nodes, macs, packet


def run_chain_case(hop_count: int, *, backoff_slots: int = 10, packet_id: int = 700):
    case = build_chain_case(
        hop_count,
        backoff_slots=backoff_slots,
        packet_id=packet_id,
    )
    simulator, _, _, metrics, coordinator, network, _, _, packet = case
    network.schedule_source_packet(packet)
    simulator.run()
    metrics.capture_coordinator(coordinator)
    return case


def main() -> None:
    results_dir = CURRENT_DIR.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    scaling_rows: list[dict[str, int | float | str]] = []

    print("=== Day07: DCF hop-scaling and metric collection ===")
    for hop_count in (2, 4, 6):
        (
            simulator,
            channel,
            config,
            metrics,
            coordinator,
            _,
            nodes,
            macs,
            packet,
        ) = run_chain_case(
            hop_count,
            backoff_slots=10,
            packet_id=700 + hop_count,
        )

        metrics.export_hop_csv(results_dir / f"dcf_{hop_count}hop_records.csv")
        metrics.export_summary_json(results_dir / f"dcf_{hop_count}hop_summary.json")

        packet_metrics = metrics.packet_summary(packet.packet_id)
        row = {
            "hop_count": hop_count,
            "packet_status": packet.status.value,
            "end_to_end_delay": float(packet.end_to_end_delay or 0.0),
            "successful_hops": metrics.successful_hops,
            "competition_attempts": packet_metrics["competition_attempts"],
            "difs_starts": packet_metrics["difs_starts"],
            "cumulative_backoff_slots": packet_metrics["cumulative_backoff_slots"],
            "cumulative_backoff_time": packet_metrics["cumulative_backoff_time"],
            "retransmissions": packet_metrics["retransmissions"],
            "shared_collision_events": coordinator.collision_count,
        }
        scaling_rows.append(row)

        expected = hop_count * config.expected_success_delay(
            packet.size_bytes,
            backoff_slots=10,
        )
        print(
            f"{hop_count} hops | delay={packet.end_to_end_delay:.9f}s | "
            f"expected={expected:.9f}s | competitions={metrics.competition_attempts} | "
            f"DIFS={metrics.difs_starts} | backoff_slots={metrics.consumed_backoff_slots}"
        )
        print(
            f"           delivered={metrics.delivered_packets}, "
            f"queues_empty={all(node.queue_is_empty for node in nodes[:-1])}, "
            f"channel_idle={channel.is_idle(simulator.now)}"
        )

    scaling_path = results_dir / "dcf_hop_scaling.csv"
    with scaling_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scaling_rows[0].keys()))
        writer.writeheader()
        writer.writerows(scaling_rows)

    print(f"\nSaved scaling results: {scaling_path}")


if __name__ == "__main__":
    main()
