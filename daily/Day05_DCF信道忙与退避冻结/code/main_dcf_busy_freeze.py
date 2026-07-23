"""Run the Day05 backoff-freeze demonstration."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
for path in (CURRENT_DIR, DAY03_CODE, DAY04_CODE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from channel import Channel
from metrics import MetricsCollector
from node import Node
from packet import Packet
from simulator import Simulator
from dcf_config import DCFConfig
from dcf_busy_mac import DCFBusyMac


def get_delivery_ratio(metrics: MetricsCollector) -> float:
    value = getattr(metrics, "delivery_ratio", None)
    if value is not None:
        return float(value() if callable(value) else value)
    created = int(getattr(metrics, "created_packets", 0))
    delivered = int(getattr(metrics, "delivered_packets", 0))
    return delivered / created if created > 0 else 0.0


def main() -> None:
    simulator = Simulator()
    channel = Channel()
    metrics = MetricsCollector()
    sender = Node(node_id=0)
    sender.neighbors.add(1)

    mac = DCFBusyMac(
        simulator=simulator,
        node=sender,
        channel=channel,
        metrics=metrics,
        config=DCFConfig(random_seed=7),
    )
    packet = Packet(
        packet_id=1,
        source=0,
        destination=1,
        created_at=0.0,
        size_bytes=1024,
        route=(0, 1),
    )

    # DIFS ends at 50 us. With seed 7, the initial backoff is 10 slots.
    # The external transmission begins at 100 us, after two slots have elapsed,
    # and keeps the medium busy for 100 us. Eight slots therefore remain frozen.
    mac.schedule_packet_arrival(packet)
    mac.schedule_external_busy(start_time=100e-6, duration=100e-6, owner=-1)
    simulator.run()

    print("=== Day05 DCF busy/freeze trace ===")
    for record in mac.trace:
        detail = f" | {record.detail}" if record.detail else ""
        print(f"{record.time:0.9f}s | {record.event:<20} | packet={record.packet_id}{detail}")

    print("\n=== Result ===")
    print(f"initial_backoff_slots : 10")
    print(f"frozen_slots          : 8")
    print(f"packet_status         : {packet.status.value}")
    print(f"end_to_end_delay      : {packet.end_to_end_delay:.9f}s")
    print(f"node_queue_length     : {sender.queue_length}")
    print(f"node_mac_state        : {sender.mac_state.value}")
    print(f"channel_idle          : {channel.is_idle(simulator.now)}")
    print(f"delivery_ratio        : {get_delivery_ratio(metrics):.3f}")


if __name__ == "__main__":
    main()
