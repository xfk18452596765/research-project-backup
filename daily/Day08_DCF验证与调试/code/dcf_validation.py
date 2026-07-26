"""Day08: validation and debugging utilities for the multi-hop DCF baseline.

This module extends the merged Day07 implementation without modifying Day03-Day07.

Day08 additions:
1. preserve concrete event names for schedule_at calls (remove GENERIC logs);
2. separate queueing delay from head-of-line channel-access delay;
3. support reproducible periodic multi-packet chain experiments;
4. provide low/medium/high load validation summaries;
5. retain Day06 collision/retry and Day07 multi-hop behavior.

No path reservation, Fixed-PRMAC, or reinforcement learning is implemented here.
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]

DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
DAY05_CODE = DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
DAY06_CODE = DAILY_DIR / "Day06_DCF碰撞与重传" / "code"
DAY07_CODE = DAILY_DIR / "Day07_DCF指标采集" / "code"

for path in (
    CURRENT_DIR,
    DAY03_CODE,
    DAY04_CODE,
    DAY05_CODE,
    DAY06_CODE,
    DAY07_CODE,
):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

from node import Node  # type: ignore  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from dcf_config import DCFConfig  # type: ignore  # noqa: E402
from dcf_multihop_metrics import (  # type: ignore  # noqa: E402
    CollisionChannel,
    DCFContentionCoordinator,
    DCFMetricsCollector,
    DCFMultiHopMac,
    DCFMultiHopNetwork,
    HopMetrics,
    SequenceRandom,
)


@dataclass(frozen=True, slots=True)
class LoadProfile:
    """Periodic source traffic used for Day08 validation."""

    name: str
    interarrival_time: float

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Load profile name cannot be empty.")
        if self.interarrival_time <= 0:
            raise ValueError("interarrival_time must be positive.")


LOAD_PROFILES: tuple[LoadProfile, ...] = (
    LoadProfile("low", 0.050),
    LoadProfile("medium", 0.020),
    LoadProfile("high", 0.008),
)


class DCFValidationMetricsCollector(DCFMetricsCollector):
    """Day07 metrics with a corrected queue/access-delay boundary.

    Day07 used ``first_DIFS_START - queue_enter_at`` as queueing delay. That is
    correct only when the head-of-line packet can start DIFS immediately. Under
    contention, a head-of-line packet may wait for a busy medium before DIFS.
    Day08 records the first time the packet becomes head-of-line:

    queue_delay = head_of_line_at - queue_enter_at
    access_delay = successful_tx_start_at - head_of_line_at
    """

    def __init__(self, *, slot_time: float) -> None:
        super().__init__(slot_time=slot_time)
        self._head_of_line_times: dict[tuple[int, int], float] = {}
        self._completed_head_of_line_times: dict[tuple[int, int], float] = {}

    def record_head_of_line(self, packet: Packet, *, at: float) -> None:
        """Record the first instant that one hop becomes head-of-line."""
        key = self._key(packet)
        self._head_of_line_times.setdefault(key, float(at))

    def record_hop_success(
        self,
        packet: Packet,
        *,
        sender: int,
        receiver: int,
        ack_at: float,
    ) -> HopMetrics:
        key = self._key(packet)
        head_of_line_at = self._head_of_line_times.pop(key, None)
        record = super().record_hop_success(
            packet,
            sender=sender,
            receiver=receiver,
            ack_at=ack_at,
        )

        if head_of_line_at is None:
            # Compatibility fallback. In Day08 experiments this path should not
            # be used because DCFValidatedMultiHopMac records HOL explicitly.
            head_of_line_at = record.first_difs_start_at

        if head_of_line_at < record.queue_enter_at:
            raise RuntimeError("head_of_line_at cannot precede queue_enter_at.")
        if record.successful_tx_start_at < head_of_line_at:
            raise RuntimeError("TX_START cannot precede head-of-line time.")

        record.queue_delay = head_of_line_at - record.queue_enter_at
        record.access_delay = record.successful_tx_start_at - head_of_line_at
        self._completed_head_of_line_times[key] = head_of_line_at
        return record

    def record_hop_drop(self, packet: Packet) -> None:
        self._head_of_line_times.pop(self._key(packet), None)
        super().record_hop_drop(packet)

    @property
    def maximum_decomposition_error(self) -> float:
        """Return max |hop - (queue + access + tx/ack)| across successful hops."""
        if not self.hop_records:
            return 0.0
        return max(
            abs(
                record.hop_delay
                - (record.queue_delay + record.access_delay + record.tx_ack_delay)
            )
            for record in self.hop_records
        )

    def summary(self) -> dict[str, float | int]:
        result = dict(super().summary())
        result["maximum_decomposition_error"] = float(
            self.maximum_decomposition_error
        )
        result["average_queue_delay"] = _mean_or_zero(
            record.queue_delay for record in self.hop_records
        )
        result["average_access_delay"] = _mean_or_zero(
            record.access_delay for record in self.hop_records
        )
        result["average_tx_ack_delay"] = _mean_or_zero(
            record.tx_ack_delay for record in self.hop_records
        )
        return result

    def export_hop_csv(self, path: str | Path) -> Path:
        """Export Day07 fields plus the explicit head-of-line timestamp."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "packet_id",
            "hop_index",
            "sender",
            "receiver",
            "queue_enter_at",
            "head_of_line_at",
            "first_difs_start_at",
            "successful_tx_start_at",
            "ack_at",
            "queue_delay",
            "access_delay",
            "tx_ack_delay",
            "hop_delay",
            "difs_starts",
            "competition_attempts",
            "selected_backoff_slots",
            "consumed_backoff_slots",
            "backoff_freezes",
            "retries",
        ]
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.hop_records:
                row = asdict(record)
                key = (record.packet_id, record.hop_index)
                row["head_of_line_at"] = self._completed_head_of_line_times.get(
                    key,
                    record.first_difs_start_at,
                )
                writer.writerow(row)
        return destination


class DCFValidatedMultiHopMac(DCFMultiHopMac):
    """Day07 MAC with Day08 event-label and HOL instrumentation fixes."""

    def _schedule_at(
        self,
        time: float,
        callback: Callable[[], None],
        *,
        event_type: str,
        priority: int,
    ) -> Any:
        """Preserve event_type through Simulator.schedule_at(**options).

        Day04's compatibility helper inspected the explicit signature of
        ``schedule_at``. The actual Day03 method receives event metadata through
        ``**options``, so those names were lost and appeared as GENERIC. Day08
        passes the metadata directly without changing the stable Day03-Day07 files.
        """
        return self.simulator.schedule_at(
            time,
            callback,
            event_type=event_type,
            priority=priority,
        )

    def _start_difs(self, packet: Packet) -> None:
        if isinstance(self.metrics, DCFValidationMetricsCollector):
            self.metrics.record_head_of_line(packet, at=self.now)
        super()._start_difs(packet)


@dataclass(slots=True)
class PeriodicChainCase:
    simulator: Simulator
    channel: CollisionChannel
    config: DCFConfig
    metrics: DCFValidationMetricsCollector
    coordinator: DCFContentionCoordinator
    network: DCFMultiHopNetwork
    nodes: list[Node]
    macs: list[DCFValidatedMultiHopMac]
    packets: list[Packet]
    hop_count: int
    packet_count: int
    interarrival_time: float
    seed: int


def build_periodic_chain_case(
    hop_count: int,
    *,
    packet_count: int,
    interarrival_time: float,
    seed: int,
    packet_size_bytes: int = 1024,
    retry_limit: int = 7,
    queue_limit: int = 200,
    log_enabled: bool = False,
) -> PeriodicChainCase:
    """Build a fixed-route periodic multi-packet chain."""

    if hop_count <= 0:
        raise ValueError("hop_count must be positive.")
    if packet_count <= 0:
        raise ValueError("packet_count must be positive.")
    if interarrival_time <= 0:
        raise ValueError("interarrival_time must be positive.")
    if packet_size_bytes <= 0:
        raise ValueError("packet_size_bytes must be positive.")
    if queue_limit <= 0:
        raise ValueError("queue_limit must be positive.")

    simulator = Simulator()
    simulator.log_enabled = bool(log_enabled)

    channel = CollisionChannel()
    config = DCFConfig(retry_limit=retry_limit)
    metrics = DCFValidationMetricsCollector(slot_time=config.slot_time)
    coordinator = DCFContentionCoordinator(simulator, channel, config)
    network = DCFMultiHopNetwork(simulator=simulator, metrics=metrics)

    nodes = [
        Node(node_id=node_id, queue_limit=queue_limit)
        for node_id in range(hop_count + 1)
    ]
    macs: list[DCFValidatedMultiHopMac] = []

    for sender in range(hop_count):
        nodes[sender].neighbors.add(sender + 1)
        station_rng = random.Random(seed + 1009 * sender)
        macs.append(
            DCFValidatedMultiHopMac(
                simulator=simulator,
                node=nodes[sender],
                channel=channel,
                metrics=metrics,
                config=config,
                rng=station_rng,
                coordinator=coordinator,
                network=network,
            )
        )

    route = tuple(range(hop_count + 1))
    packets: list[Packet] = []
    packet_id_base = 800_000 + seed * 1_000 + hop_count * 100

    for index in range(packet_count):
        arrival_time = index * interarrival_time
        packet = Packet(
            packet_id=packet_id_base + index,
            source=0,
            destination=hop_count,
            created_at=arrival_time,
            size_bytes=packet_size_bytes,
            route=route,
        )
        packets.append(packet)
        network.schedule_source_packet(packet, at=arrival_time)

    return PeriodicChainCase(
        simulator=simulator,
        channel=channel,
        config=config,
        metrics=metrics,
        coordinator=coordinator,
        network=network,
        nodes=nodes,
        macs=macs,
        packets=packets,
        hop_count=hop_count,
        packet_count=packet_count,
        interarrival_time=interarrival_time,
        seed=seed,
    )


def run_periodic_chain_case(
    hop_count: int,
    *,
    packet_count: int,
    interarrival_time: float,
    seed: int,
    packet_size_bytes: int = 1024,
    retry_limit: int = 7,
    queue_limit: int = 200,
    log_enabled: bool = False,
) -> tuple[PeriodicChainCase, dict[str, int | float | str]]:
    case = build_periodic_chain_case(
        hop_count,
        packet_count=packet_count,
        interarrival_time=interarrival_time,
        seed=seed,
        packet_size_bytes=packet_size_bytes,
        retry_limit=retry_limit,
        queue_limit=queue_limit,
        log_enabled=log_enabled,
    )

    case.simulator.run()
    case.metrics.capture_coordinator(case.coordinator)
    result = summarize_periodic_case(case)
    return case, result


def summarize_periodic_case(
    case: PeriodicChainCase,
) -> dict[str, int | float | str]:
    delivered_packets = [
        packet
        for packet in case.packets
        if packet.status == PacketStatus.DELIVERED
        and packet.end_to_end_delay is not None
    ]
    delays = [float(packet.end_to_end_delay) for packet in delivered_packets]
    simulation_time = float(case.simulator.now)
    delivered_payload_bits = sum(
        int(packet.size_bytes) * 8 for packet in delivered_packets
    )

    return {
        "hop_count": int(case.hop_count),
        "packet_count": int(case.packet_count),
        "interarrival_time": float(case.interarrival_time),
        "seed": int(case.seed),
        "simulation_time": simulation_time,
        "created_packets": int(case.metrics.created_packets),
        "delivered_packets": int(case.metrics.delivered_packets),
        "dropped_packets": int(case.metrics.dropped_packets),
        "delivery_ratio": (
            float(case.metrics.delivered_packets / case.metrics.created_packets)
            if case.metrics.created_packets
            else 0.0
        ),
        "average_end_to_end_delay": _mean_or_zero(delays),
        "p95_end_to_end_delay": _percentile(delays, 0.95),
        "maximum_end_to_end_delay": max(delays, default=0.0),
        "throughput_bps": (
            float(delivered_payload_bits / simulation_time)
            if simulation_time > 0
            else 0.0
        ),
        "successful_hops": int(case.metrics.successful_hops),
        "shared_collision_events": int(case.coordinator.collision_count),
        "collided_packet_attempts": int(case.metrics.collided_packet_attempts),
        "retransmissions": int(case.metrics.retransmissions),
        "ack_timeouts": int(case.metrics.ack_timeouts),
        "difs_starts": int(case.metrics.difs_starts),
        "competition_attempts": int(case.metrics.competition_attempts),
        "backoff_freezes": int(case.metrics.backoff_freezes),
        "average_queue_delay": _mean_or_zero(
            record.queue_delay for record in case.metrics.hop_records
        ),
        "average_access_delay": _mean_or_zero(
            record.access_delay for record in case.metrics.hop_records
        ),
        "average_tx_ack_delay": _mean_or_zero(
            record.tx_ack_delay for record in case.metrics.hop_records
        ),
        "maximum_decomposition_error": float(
            case.metrics.maximum_decomposition_error
        ),
        "queues_empty": int(
            all(node.queue_is_empty for node in case.nodes[:-1])
        ),
        "channel_idle": int(case.channel.is_idle(case.simulator.now)),
    }


def run_converging_collision_smoke(
    *,
    log_enabled: bool = False,
) -> tuple[dict[str, Any], dict[str, int | float | str]]:
    """Run two 2-hop flows sharing relay 2.

    Routes:
        0 -> 2 -> 3
        1 -> 2 -> 3

    The first source attempts are both zero-slot and therefore collide.
    """

    simulator = Simulator()
    simulator.log_enabled = bool(log_enabled)
    channel = CollisionChannel()
    config = DCFConfig()
    metrics = DCFValidationMetricsCollector(slot_time=config.slot_time)
    coordinator = DCFContentionCoordinator(simulator, channel, config)
    network = DCFMultiHopNetwork(simulator=simulator, metrics=metrics)

    nodes = [Node(node_id=index) for index in range(4)]
    nodes[0].neighbors.add(2)
    nodes[1].neighbors.add(2)
    nodes[2].neighbors.add(3)

    mac0 = DCFValidatedMultiHopMac(
        simulator=simulator,
        node=nodes[0],
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 0]),
        coordinator=coordinator,
        network=network,
    )
    mac1 = DCFValidatedMultiHopMac(
        simulator=simulator,
        node=nodes[1],
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 1]),
        coordinator=coordinator,
        network=network,
    )
    relay_mac = DCFValidatedMultiHopMac(
        simulator=simulator,
        node=nodes[2],
        channel=channel,
        metrics=metrics,
        config=config,
        rng=SequenceRandom([0, 0]),
        coordinator=coordinator,
        network=network,
    )

    packet0 = Packet(
        packet_id=880,
        source=0,
        destination=3,
        created_at=0.0,
        route=(0, 2, 3),
    )
    packet1 = Packet(
        packet_id=881,
        source=1,
        destination=3,
        created_at=0.0,
        route=(1, 2, 3),
    )

    network.schedule_source_packet(packet0)
    network.schedule_source_packet(packet1)
    simulator.run()
    metrics.capture_coordinator(coordinator)

    delays = [
        float(packet.end_to_end_delay)
        for packet in (packet0, packet1)
        if packet.end_to_end_delay is not None
    ]
    result: dict[str, int | float | str] = {
        "created_packets": int(metrics.created_packets),
        "delivered_packets": int(metrics.delivered_packets),
        "dropped_packets": int(metrics.dropped_packets),
        "successful_hops": int(metrics.successful_hops),
        "shared_collision_events": int(coordinator.collision_count),
        "collided_packet_attempts": int(metrics.collided_packet_attempts),
        "retransmissions": int(metrics.retransmissions),
        "backoff_freezes": int(metrics.backoff_freezes),
        "average_end_to_end_delay": _mean_or_zero(delays),
        "maximum_decomposition_error": float(
            metrics.maximum_decomposition_error
        ),
        "queues_empty": int(all(node.queue_is_empty for node in nodes[:-1])),
        "channel_idle": int(channel.is_idle(simulator.now)),
    }
    context = {
        "simulator": simulator,
        "channel": channel,
        "config": config,
        "metrics": metrics,
        "coordinator": coordinator,
        "network": network,
        "nodes": nodes,
        "macs": [mac0, mac1, relay_mac],
        "packets": [packet0, packet1],
    }
    return context, result


def aggregate_validation_rows(
    rows: Iterable[dict[str, int | float | str]],
) -> list[dict[str, int | float | str]]:
    grouped: dict[tuple[int, str], list[dict[str, int | float | str]]] = defaultdict(list)
    for row in rows:
        key = (int(row["hop_count"]), str(row["load_level"]))
        grouped[key].append(row)

    aggregates: list[dict[str, int | float | str]] = []
    for (hop_count, load_level), group in sorted(grouped.items()):
        aggregates.append(
            {
                "hop_count": hop_count,
                "load_level": load_level,
                "interarrival_time": float(group[0]["interarrival_time"]),
                "seed_count": len(group),
                "mean_delivery_ratio": _mean_or_zero(
                    float(row["delivery_ratio"]) for row in group
                ),
                "mean_end_to_end_delay": _mean_or_zero(
                    float(row["average_end_to_end_delay"]) for row in group
                ),
                "std_end_to_end_delay": _sample_std_or_zero(
                    float(row["average_end_to_end_delay"]) for row in group
                ),
                "mean_p95_end_to_end_delay": _mean_or_zero(
                    float(row["p95_end_to_end_delay"]) for row in group
                ),
                "mean_throughput_bps": _mean_or_zero(
                    float(row["throughput_bps"]) for row in group
                ),
                "mean_collision_events": _mean_or_zero(
                    float(row["shared_collision_events"]) for row in group
                ),
                "mean_retransmissions": _mean_or_zero(
                    float(row["retransmissions"]) for row in group
                ),
                "mean_queue_delay": _mean_or_zero(
                    float(row["average_queue_delay"]) for row in group
                ),
                "mean_access_delay": _mean_or_zero(
                    float(row["average_access_delay"]) for row in group
                ),
                "max_decomposition_error": max(
                    float(row["maximum_decomposition_error"]) for row in group
                ),
            }
        )
    return aggregates


def write_csv(
    path: str | Path,
    rows: list[dict[str, int | float | str]],
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("Cannot write an empty CSV.")
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return destination


def write_json(path: str | Path, payload: Any) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination


def _mean_or_zero(values: Iterable[float]) -> float:
    data = [float(value) for value in values]
    return float(statistics.mean(data)) if data else 0.0


def _sample_std_or_zero(values: Iterable[float]) -> float:
    data = [float(value) for value in values]
    return float(statistics.stdev(data)) if len(data) >= 2 else 0.0


def _percentile(values: Iterable[float], probability: float) -> float:
    data = sorted(float(value) for value in values)
    if not data:
        return 0.0
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1].")
    if len(data) == 1:
        return data[0]

    position = probability * (len(data) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return data[lower_index]
    fraction = position - lower_index
    return data[lower_index] + fraction * (
        data[upper_index] - data[lower_index]
    )


__all__ = [
    "DCFValidatedMultiHopMac",
    "DCFValidationMetricsCollector",
    "LOAD_PROFILES",
    "LoadProfile",
    "PeriodicChainCase",
    "aggregate_validation_rows",
    "build_periodic_chain_case",
    "run_converging_collision_smoke",
    "run_periodic_chain_case",
    "summarize_periodic_case",
    "write_csv",
    "write_json",
]
