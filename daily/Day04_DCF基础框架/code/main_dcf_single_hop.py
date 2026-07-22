"""Run the Day04 minimum single-hop DCF example."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAY03_CODE = CURRENT_DIR.parents[1] / "Day03_仿真架构与事件设计" / "code"
for path in (CURRENT_DIR, DAY03_CODE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from channel import Channel
from metrics import MetricsCollector
from node import Node
from packet import Packet
from simulator import Simulator

from dcf_config import DCFConfig
from dcf_mac import DCFMac


def get_delivery_ratio(metrics: MetricsCollector) -> float:
    """Read delivery ratio without assuming Day03 exposes it as a property."""
    value = getattr(metrics, "delivery_ratio", None)
    if value is not None:
        return float(value() if callable(value) else value)

    for method_name in ("summary", "get_summary", "report"):
        method = getattr(metrics, method_name, None)
        if not callable(method):
            continue
        result = method()
        if isinstance(result, dict):
            for key in ("delivery_ratio", "packet_delivery_ratio", "delivery_rate"):
                if key in result:
                    return float(result[key])

    created = int(getattr(metrics, "created_packets", 0))
    delivered = int(getattr(metrics, "delivered_packets", 0))
    return delivered / created if created > 0 else 0.0


def main() -> None:
    simulator = Simulator()
    channel = Channel()
    metrics = MetricsCollector()
    sender = Node(node_id=0)
    sender.neighbors.add(1)

    config = DCFConfig(random_seed=7)
    dcf = DCFMac(
        simulator=simulator,
        node=sender,
        channel=channel,
        metrics=metrics,
        config=config,
    )

    packet = Packet(
        packet_id=1,
        source=0,
        destination=1,
        created_at=0.0,
        size_bytes=1024,
        priority=0,
        route=(0, 1),
    )

    dcf.schedule_packet_arrival(packet)
    simulator.run()

    print("=== Day04 minimum DCF trace ===")
    for record in dcf.trace:
        detail = f" | {record.detail}" if record.detail else ""
        print(f"{record.time:0.9f}s | {record.event:<16} | packet={record.packet_id}{detail}")

    print("\n=== Result ===")
    print(f"packet_status       : {packet.status.value}")
    print(f"end_to_end_delay    : {packet.end_to_end_delay:.9f}s")
    print(f"node_queue_length   : {sender.queue_length}")
    print(f"node_mac_state      : {sender.mac_state.value}")
    print(f"channel_idle        : {channel.is_idle(simulator.now)}")
    print(f"delivery_ratio      : {get_delivery_ratio(metrics):.3f}")


if __name__ == "__main__":
    main()
