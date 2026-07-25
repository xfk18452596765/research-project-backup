"""Run the Day06 two-sender collision and retransmission demonstration."""

from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
DAY05_CODE = DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
for path in (CURRENT_DIR, DAY03_CODE, DAY04_CODE, DAY05_CODE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from metrics import MetricsCollector
from node import Node
from packet import Packet
from simulator import Simulator
from dcf_config import DCFConfig
from dcf_collision_mac import (
    CollisionChannel,
    DCFContentionCoordinator,
    DCFContentionMac,
    SequenceRandom,
)


def get_delivery_ratio(metrics: MetricsCollector) -> float:
    value = getattr(metrics, "delivery_ratio", None)
    if value is not None:
        return float(value() if callable(value) else value)
    created = int(getattr(metrics, "created_packets", 0))
    delivered = int(getattr(metrics, "delivered_packets", 0))
    return delivered / created if created > 0 else 0.0


def print_trace(label: str, mac: DCFContentionMac) -> None:
    print(f"\n=== {label} trace ===")
    for record in mac.trace:
        detail = f" | {record.detail}" if record.detail else ""
        print(
            f"{record.time:0.9f}s | node={record.node_id} | "
            f"{record.event:<18} | packet={record.packet_id}{detail}"
        )


def main() -> None:
    simulator = Simulator()
    channel = CollisionChannel()
    metrics = MetricsCollector()
    config = DCFConfig(retry_limit=7)
    coordinator = DCFContentionCoordinator(simulator, channel, config)

    sender0 = Node(node_id=0)
    sender1 = Node(node_id=1)
    sender0.neighbors.add(2)
    sender1.neighbors.add(2)

    # First attempt: both choose 0, so they transmit in the same slot and collide.
    # Retry: sender0 chooses 0 while sender1 chooses 1. Sender0 succeeds first;
    # sender1 freezes its one slot and resumes after sender0's ACK.
    mac0 = DCFContentionMac(
        simulator=simulator,
        node=sender0,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 0]),
        coordinator=coordinator,
    )
    mac1 = DCFContentionMac(
        simulator=simulator,
        node=sender1,
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 1]),
        coordinator=coordinator,
    )

    packet0 = Packet(
        packet_id=1,
        source=0,
        destination=2,
        created_at=0.0,
        size_bytes=1024,
        route=(0, 2),
    )
    packet1 = Packet(
        packet_id=2,
        source=1,
        destination=2,
        created_at=0.0,
        size_bytes=1024,
        route=(1, 2),
    )

    mac0.schedule_packet_arrival(packet0)
    mac1.schedule_packet_arrival(packet1)
    simulator.run()

    print_trace("Sender 0", mac0)
    print_trace("Sender 1", mac1)

    print("\n=== Result ===")
    print(f"collision_count       : {coordinator.collision_count}")
    print(f"successful_exchanges  : {coordinator.successful_exchange_count}")
    print(f"packet0_status        : {packet0.status.value}")
    print(f"packet0_retries       : {packet0.retries}")
    print(f"packet0_delay         : {packet0.end_to_end_delay:.9f}s")
    print(f"packet1_status        : {packet1.status.value}")
    print(f"packet1_retries       : {packet1.retries}")
    print(f"packet1_delay         : {packet1.end_to_end_delay:.9f}s")
    print(f"node0_mac_state       : {sender0.mac_state.value}")
    print(f"node1_mac_state       : {sender1.mac_state.value}")
    print(f"channel_idle          : {channel.is_idle(simulator.now)}")
    print(f"delivery_ratio        : {get_delivery_ratio(metrics):.3f}")


if __name__ == "__main__":
    main()
