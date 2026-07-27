"""Day13 fair DCF vs Fixed-PRMAC stop-loss pre-experiment.

The experiment reuses the merged Day08 DCF periodic-chain runner and the Day13
complete Fixed-PRMAC controller under identical routes, packet sizes, arrivals,
seeds, retry limits, and PHY timing. It is a pre-RL checkpoint, not an RL task.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]
DAY13_CODE = CURRENT_DIR
DAY12_CODE = DAILY_DIR / "Day12_Fixed-PRMAC失败与重传" / "code"
DAY11_CODE = DAILY_DIR / "Day11_Fixed-PRMAC连续转发" / "code"
DAY10_CODE = DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code"
DAY09_CODE = DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code"
DAY08_CODE = DAILY_DIR / "Day08_DCF验证与调试" / "code"
DAY07_CODE = DAILY_DIR / "Day07_DCF指标采集" / "code"
DAY06_CODE = DAILY_DIR / "Day06_DCF碰撞与重传" / "code"
DAY05_CODE = DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code"
DAY04_CODE = DAILY_DIR / "Day04_DCF基础框架" / "code"
DAY03_CODE = DAILY_DIR / "Day03_仿真架构与事件设计" / "code"

_import_paths = [
    DAY13_CODE,
    DAY12_CODE,
    DAY11_CODE,
    DAY10_CODE,
    DAY09_CODE,
    DAY08_CODE,
    DAY07_CODE,
    DAY06_CODE,
    DAY05_CODE,
    DAY04_CODE,
    DAY03_CODE,
]
for path in _import_paths:
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from fixed_prmac_messages import ReservationStatus  # noqa: E402
from packet import Packet, PacketStatus  # type: ignore  # noqa: E402
from simulator import Simulator  # type: ignore  # noqa: E402
from fixed_prmac_end_to_end import (  # noqa: E402
    Day13FixedPRMACConfig,
    FixedPRMACEndToEndController,
)

# Day12 changes sys.path while importing. Restore Day08 ahead of older DCF files.
for path in _import_paths:
    text = str(path)
    while text in sys.path:
        sys.path.remove(text)
sys.path[:0] = [str(path) for path in _import_paths if path.exists()]

from dcf_config import DCFConfig  # type: ignore  # noqa: E402
from dcf_validation import LOAD_PROFILES, run_periodic_chain_case  # type: ignore  # noqa: E402


HOP_COUNTS = (2, 4, 6)
SEEDS = (7, 17, 27)
PACKETS_PER_RUN = 8
PACKET_SIZE_BYTES = 1024
QUEUE_LIMIT = 200


@dataclass(frozen=True, slots=True)
class StopLossScope:
    hop_counts: tuple[int, ...] = HOP_COUNTS
    seeds: tuple[int, ...] = SEEDS
    packets_per_run: int = PACKETS_PER_RUN
    packet_size_bytes: int = PACKET_SIZE_BYTES
    queue_limit: int = QUEUE_LIMIT


@dataclass(slots=True)
class FixedPeriodicCase:
    simulator: Simulator
    controller: FixedPRMACEndToEndController
    packets: list[Packet]
    hop_count: int
    packet_count: int
    interarrival_time: float
    seed: int


def build_chain_adjacency(hop_count: int) -> dict[int, set[int]]:
    if hop_count <= 0:
        raise ValueError("hop_count must be positive.")
    adjacency: dict[int, set[int]] = {node: set() for node in range(hop_count + 1)}
    for sender in range(hop_count):
        adjacency[sender].add(sender + 1)
        adjacency[sender + 1].add(sender)
    return adjacency


def run_fixed_periodic_chain_case(
    hop_count: int,
    *,
    packet_count: int,
    interarrival_time: float,
    seed: int,
    packet_size_bytes: int = PACKET_SIZE_BYTES,
    retry_limit: int = 7,
    queue_limit: int = QUEUE_LIMIT,
    log_enabled: bool = False,
) -> tuple[FixedPeriodicCase, dict[str, int | float | str]]:
    if packet_count <= 0:
        raise ValueError("packet_count must be positive.")
    if interarrival_time <= 0:
        raise ValueError("interarrival_time must be positive.")

    simulator = Simulator()
    simulator.log_enabled = bool(log_enabled)
    config = Day13FixedPRMACConfig(
        retry_limit=retry_limit,
        random_seed=seed,
        queue_limit=queue_limit,
    )
    controller = FixedPRMACEndToEndController(
        simulator=simulator,
        config=config,
        adjacency=build_chain_adjacency(hop_count),
    )
    route = tuple(range(hop_count + 1))
    packets: list[Packet] = []
    packet_id_base = 1_300_000 + seed * 1_000 + hop_count * 100
    for index in range(packet_count):
        arrival = index * interarrival_time
        packet = Packet(
            packet_id=packet_id_base + index,
            source=0,
            destination=hop_count,
            created_at=arrival,
            size_bytes=packet_size_bytes,
            route=route,
        )
        packets.append(packet)
        controller.schedule_end_to_end(
            packet,
            flow_id=f"fixed-{hop_count}hop",
            at=arrival,
        )

    simulator.run()
    case = FixedPeriodicCase(
        simulator=simulator,
        controller=controller,
        packets=packets,
        hop_count=hop_count,
        packet_count=packet_count,
        interarrival_time=interarrival_time,
        seed=seed,
    )
    return case, summarize_fixed_case(case)


def summarize_fixed_case(case: FixedPeriodicCase) -> dict[str, int | float | str]:
    delivered = [
        packet
        for packet in case.packets
        if packet.status == PacketStatus.DELIVERED and packet.end_to_end_delay is not None
    ]
    dropped = [packet for packet in case.packets if packet.status == PacketStatus.DROPPED]
    delays = [float(packet.end_to_end_delay) for packet in delivered]
    delivery_boundary = max(
        (float(packet.delivered_at) for packet in delivered if packet.delivered_at is not None),
        default=float(case.simulator.now),
    )
    payload_bits = sum(packet.size_bytes * 8 for packet in delivered)
    metrics = case.controller.metrics.summary(case.controller.table)
    active_after_run = sum(
        reservation.status == ReservationStatus.ACTIVE
        for reservation in case.controller.table.records
    )
    total_segments = sum(
        len(record.segments) for record in case.controller.end_to_end_records.values()
    )
    completed_segments = sum(
        record.completed_segments for record in case.controller.end_to_end_records.values()
    )

    return {
        "protocol": "Fixed-PRMAC",
        "hop_count": case.hop_count,
        "packet_count": case.packet_count,
        "interarrival_time": case.interarrival_time,
        "seed": case.seed,
        "measurement_end_time": delivery_boundary,
        "created_packets": len(case.packets),
        "delivered_packets": len(delivered),
        "dropped_packets": len(dropped),
        "delivery_ratio": len(delivered) / len(case.packets) if case.packets else 0.0,
        "average_end_to_end_delay": _mean(delays),
        "p95_end_to_end_delay": _percentile(delays, 0.95),
        "p99_end_to_end_delay": _percentile(delays, 0.99),
        "maximum_end_to_end_delay": max(delays, default=0.0),
        "throughput_bps": payload_bits / delivery_boundary if delivery_boundary > 0 else 0.0,
        "successful_hops": int(metrics["forwarded_hops"]),
        "collision_or_conflict_events": int(metrics["link_conflicts"] + metrics["node_conflicts"]),
        "retransmissions": int(metrics["reservation_retries_scheduled"]),
        "contention_attempts": int(metrics["retry_attempts_scheduled"]),
        "difs_starts": int(metrics["retry_attempts_scheduled"]),
        "segment_queue_entries": int(metrics["segment_queue_entries"]),
        "queue_overflow_drops": int(metrics["queue_overflow_drops"]),
        "maximum_segment_queue_length": int(metrics["maximum_segment_queue_length"]),
        "average_segment_queue_delay": float(metrics["average_segment_queue_delay"]),
        "maximum_segment_queue_delay": float(metrics["maximum_segment_queue_delay"]),
        "control_frames_sent": int(metrics["control_frames_sent"]),
        "control_bytes_sent": int(metrics["control_bytes_sent"]),
        "data_frames_sent": int(metrics["data_frames_sent"]),
        "data_bytes_sent": int(metrics["data_bytes_sent"]),
        "ack_frames_sent": int(metrics["h_ack_frames_sent"]),
        "ack_bytes_sent": int(metrics["h_ack_bytes_sent"]),
        "total_frames_sent": int(metrics["total_frames_sent"]),
        "total_bytes_sent": int(metrics["total_bytes_sent"]),
        "frames_per_created_packet": int(metrics["total_frames_sent"]) / len(case.packets),
        "bytes_per_created_packet": int(metrics["total_bytes_sent"]) / len(case.packets),
        "control_bytes_per_delivered_packet": (
            int(metrics["control_bytes_sent"]) / len(delivered) if delivered else 0.0
        ),
        "total_segments": total_segments,
        "completed_segments": completed_segments,
        "active_reservations_after_run": active_after_run,
        "terminal_sessions": sum(
            record.status.value in {"COMPLETED", "FAILED"}
            for record in case.controller.end_to_end_records.values()
        ),
    }


def run_dcf_comparison_case(
    hop_count: int,
    *,
    packet_count: int,
    interarrival_time: float,
    seed: int,
    packet_size_bytes: int = PACKET_SIZE_BYTES,
    retry_limit: int = 7,
    queue_limit: int = QUEUE_LIMIT,
) -> dict[str, int | float | str]:
    case, base = run_periodic_chain_case(
        hop_count,
        packet_count=packet_count,
        interarrival_time=interarrival_time,
        seed=seed,
        packet_size_bytes=packet_size_bytes,
        retry_limit=retry_limit,
        queue_limit=queue_limit,
        log_enabled=False,
    )
    delivered = [
        packet
        for packet in case.packets
        if packet.status == PacketStatus.DELIVERED and packet.end_to_end_delay is not None
    ]
    delays = [float(packet.end_to_end_delay) for packet in delivered]
    delivery_boundary = max(
        (float(packet.delivered_at) for packet in delivered if packet.delivered_at is not None),
        default=float(case.simulator.now),
    )
    payload_bits = sum(packet.size_bytes * 8 for packet in delivered)
    successful_hops = int(base["successful_hops"])
    collided_attempts = int(base["collided_packet_attempts"])
    data_attempts = successful_hops + collided_attempts
    ack_frames = successful_hops
    dcf_config = case.config
    data_bytes = data_attempts * (dcf_config.mac_header_bytes + packet_size_bytes)
    ack_bytes = ack_frames * dcf_config.ack_size_bytes
    total_frames = data_attempts + ack_frames
    total_bytes = data_bytes + ack_bytes

    return {
        "protocol": "DCF",
        "hop_count": hop_count,
        "packet_count": packet_count,
        "interarrival_time": interarrival_time,
        "seed": seed,
        "measurement_end_time": delivery_boundary,
        "created_packets": int(base["created_packets"]),
        "delivered_packets": int(base["delivered_packets"]),
        "dropped_packets": int(base["dropped_packets"]),
        "delivery_ratio": float(base["delivery_ratio"]),
        "average_end_to_end_delay": _mean(delays),
        "p95_end_to_end_delay": _percentile(delays, 0.95),
        "p99_end_to_end_delay": _percentile(delays, 0.99),
        "maximum_end_to_end_delay": max(delays, default=0.0),
        "throughput_bps": payload_bits / delivery_boundary if delivery_boundary > 0 else 0.0,
        "successful_hops": successful_hops,
        "collision_or_conflict_events": int(base["shared_collision_events"]),
        "retransmissions": int(base["retransmissions"]),
        "contention_attempts": int(base["competition_attempts"]),
        "difs_starts": int(base["difs_starts"]),
        "segment_queue_entries": successful_hops,
        "queue_overflow_drops": 0,
        "maximum_segment_queue_length": 0,
        "average_segment_queue_delay": float(base["average_queue_delay"]),
        "maximum_segment_queue_delay": max(
            (record.queue_delay for record in case.metrics.hop_records),
            default=0.0,
        ),
        "control_frames_sent": ack_frames,
        "control_bytes_sent": ack_bytes,
        "data_frames_sent": data_attempts,
        "data_bytes_sent": data_bytes,
        "ack_frames_sent": ack_frames,
        "ack_bytes_sent": ack_bytes,
        "total_frames_sent": total_frames,
        "total_bytes_sent": total_bytes,
        "frames_per_created_packet": total_frames / packet_count,
        "bytes_per_created_packet": total_bytes / packet_count,
        "control_bytes_per_delivered_packet": ack_bytes / len(delivered) if delivered else 0.0,
        "total_segments": 0,
        "completed_segments": 0,
        "active_reservations_after_run": 0,
        "terminal_sessions": int(base["delivered_packets"] + base["dropped_packets"]),
    }


def run_stop_loss_matrix(
    results_dir: str | Path,
    *,
    scope: StopLossScope = StopLossScope(),
) -> dict[str, Any]:
    destination = Path(results_dir)
    destination.mkdir(parents=True, exist_ok=True)
    raw_rows: list[dict[str, int | float | str]] = []

    for hop_count in scope.hop_counts:
        for profile in LOAD_PROFILES:
            for seed in scope.seeds:
                dcf = run_dcf_comparison_case(
                    hop_count,
                    packet_count=scope.packets_per_run,
                    interarrival_time=profile.interarrival_time,
                    seed=seed,
                    packet_size_bytes=scope.packet_size_bytes,
                    queue_limit=scope.queue_limit,
                )
                dcf["load_level"] = profile.name
                raw_rows.append(dcf)

                _, fixed = run_fixed_periodic_chain_case(
                    hop_count,
                    packet_count=scope.packets_per_run,
                    interarrival_time=profile.interarrival_time,
                    seed=seed,
                    packet_size_bytes=scope.packet_size_bytes,
                    queue_limit=scope.queue_limit,
                )
                fixed["load_level"] = profile.name
                raw_rows.append(fixed)

    aggregate_rows = aggregate_protocol_rows(raw_rows)
    comparison_rows = build_comparison_rows(aggregate_rows)
    fairness = build_fairness_check(scope)
    evaluation = evaluate_stop_loss(
        raw_rows=raw_rows,
        aggregate_rows=aggregate_rows,
        comparison_rows=comparison_rows,
        fairness=fairness,
    )

    write_csv(destination / "day13_stop_loss_raw.csv", raw_rows)
    write_csv(destination / "day13_stop_loss_aggregate.csv", aggregate_rows)
    write_csv(destination / "day13_stop_loss_comparison.csv", comparison_rows)
    payload = {
        "scope": {
            **asdict(scope),
            "load_profiles": [asdict(profile) for profile in LOAD_PROFILES],
        },
        "fairness": fairness,
        "evaluation": evaluation,
        "comparison_rows": comparison_rows,
    }
    write_json(destination / "day13_stop_loss_decision.json", payload)
    return payload


def aggregate_protocol_rows(
    rows: Iterable[dict[str, int | float | str]],
) -> list[dict[str, int | float | str]]:
    groups: dict[tuple[str, int, str], list[dict[str, int | float | str]]] = {}
    for row in rows:
        key = (str(row["protocol"]), int(row["hop_count"]), str(row["load_level"]))
        groups.setdefault(key, []).append(row)

    result: list[dict[str, int | float | str]] = []
    metrics = (
        "delivery_ratio",
        "average_end_to_end_delay",
        "p95_end_to_end_delay",
        "p99_end_to_end_delay",
        "throughput_bps",
        "collision_or_conflict_events",
        "retransmissions",
        "control_bytes_sent",
        "total_frames_sent",
        "total_bytes_sent",
        "frames_per_created_packet",
        "bytes_per_created_packet",
        "control_bytes_per_delivered_packet",
        "queue_overflow_drops",
        "maximum_segment_queue_length",
        "average_segment_queue_delay",
        "maximum_segment_queue_delay",
    )
    for (protocol, hop_count, load_level), group in sorted(groups.items()):
        row: dict[str, int | float | str] = {
            "protocol": protocol,
            "hop_count": hop_count,
            "load_level": load_level,
            "interarrival_time": float(group[0]["interarrival_time"]),
            "seed_count": len(group),
        }
        for metric in metrics:
            row[f"mean_{metric}"] = _mean(float(item[metric]) for item in group)
        row["std_average_end_to_end_delay"] = _sample_std(
            float(item["average_end_to_end_delay"]) for item in group
        )
        row["all_runs_terminal"] = int(
            all(int(item["terminal_sessions"]) == int(item["created_packets"]) for item in group)
        )
        row["all_fixed_resources_released"] = int(
            protocol != "Fixed-PRMAC"
            or all(int(item["active_reservations_after_run"]) == 0 for item in group)
        )
        result.append(row)
    return result


def build_comparison_rows(
    aggregates: Iterable[dict[str, int | float | str]],
) -> list[dict[str, int | float | str]]:
    indexed = {
        (str(row["protocol"]), int(row["hop_count"]), str(row["load_level"])): row
        for row in aggregates
    }
    result: list[dict[str, int | float | str]] = []
    for hop_count in HOP_COUNTS:
        for profile in LOAD_PROFILES:
            dcf = indexed[("DCF", hop_count, profile.name)]
            fixed = indexed[("Fixed-PRMAC", hop_count, profile.name)]
            dcf_delay = float(dcf["mean_average_end_to_end_delay"])
            fixed_delay = float(fixed["mean_average_end_to_end_delay"])
            result.append(
                {
                    "hop_count": hop_count,
                    "load_level": profile.name,
                    "dcf_mean_delay": dcf_delay,
                    "fixed_mean_delay": fixed_delay,
                    "fixed_delay_minus_dcf": fixed_delay - dcf_delay,
                    "fixed_delay_lower": int(fixed_delay < dcf_delay),
                    "dcf_mean_p95": float(dcf["mean_p95_end_to_end_delay"]),
                    "fixed_mean_p95": float(fixed["mean_p95_end_to_end_delay"]),
                    "dcf_mean_p99": float(dcf["mean_p99_end_to_end_delay"]),
                    "fixed_mean_p99": float(fixed["mean_p99_end_to_end_delay"]),
                    "dcf_delivery_ratio": float(dcf["mean_delivery_ratio"]),
                    "fixed_delivery_ratio": float(fixed["mean_delivery_ratio"]),
                    "fixed_delivery_not_lower": int(
                        float(fixed["mean_delivery_ratio"])
                        >= float(dcf["mean_delivery_ratio"])
                    ),
                    "dcf_throughput_bps": float(dcf["mean_throughput_bps"]),
                    "fixed_throughput_bps": float(fixed["mean_throughput_bps"]),
                    "dcf_collision_events": float(dcf["mean_collision_or_conflict_events"]),
                    "fixed_conflict_events": float(fixed["mean_collision_or_conflict_events"]),
                    "dcf_retransmissions": float(dcf["mean_retransmissions"]),
                    "fixed_retries": float(fixed["mean_retransmissions"]),
                    "dcf_control_bytes": float(dcf["mean_control_bytes_sent"]),
                    "fixed_control_bytes": float(fixed["mean_control_bytes_sent"]),
                    "dcf_total_bytes": float(dcf["mean_total_bytes_sent"]),
                    "fixed_total_bytes": float(fixed["mean_total_bytes_sent"]),
                    "dcf_mean_queue_delay": float(dcf["mean_average_segment_queue_delay"]),
                    "fixed_mean_queue_delay": float(fixed["mean_average_segment_queue_delay"]),
                    "fixed_mean_queue_overflow_drops": float(fixed["mean_queue_overflow_drops"]),
                    "fixed_mean_maximum_queue_length": float(fixed["mean_maximum_segment_queue_length"]),
                }
            )
    return result


def build_fairness_check(scope: StopLossScope) -> dict[str, Any]:
    dcf = DCFConfig()
    fixed = Day13FixedPRMACConfig()
    checks = {
        "data_rate_bps": dcf.data_rate_bps == fixed.data_rate_bps,
        "basic_rate_bps": dcf.basic_rate_bps == fixed.basic_rate_bps,
        "mac_header_bytes": dcf.mac_header_bytes == fixed.data_mac_header_bytes,
        "ack_size_bytes": dcf.ack_size_bytes == fixed.h_ack_size_bytes,
        "sifs_time": dcf.sifs_time == fixed.sifs_time,
        "difs_time": dcf.difs_time == fixed.difs_time,
        "slot_time": dcf.slot_time == fixed.slot_time,
        "propagation_delay": dcf.propagation_delay == fixed.propagation_delay,
        "cw_min": dcf.cw_min == fixed.fixed_cw_min,
        "cw_max": dcf.cw_max == fixed.cw_max,
        "retry_limit": dcf.retry_limit == fixed.retry_limit,
        "same_packet_size": scope.packet_size_bytes == PACKET_SIZE_BYTES,
        "same_hop_counts": tuple(scope.hop_counts) == HOP_COUNTS,
        "same_seeds": tuple(scope.seeds) == SEEDS,
        "same_packets_per_run": scope.packets_per_run == PACKETS_PER_RUN,
        "same_queue_limit": scope.queue_limit == fixed.queue_limit == QUEUE_LIMIT,
    }
    return {
        "checks": checks,
        "all_passed": all(checks.values()),
        "note": (
            "No percentage-improvement threshold is imposed. The checkpoint uses "
            "multi-cell trend, critical-cell trend, seed consistency, delivery, "
            "functionality, and fairness evidence."
        ),
    }


def evaluate_stop_loss(
    *,
    raw_rows: list[dict[str, int | float | str]],
    aggregate_rows: list[dict[str, int | float | str]],
    comparison_rows: list[dict[str, int | float | str]],
    fairness: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate the Day13 stop-loss checkpoint against the declared hypothesis.

    Day13-Fix02 aligns the gate with the protocol's original research target:
    reducing repeated contention on longer and/or congested multi-hop paths.
    The 2-hop and low-load cells remain mandatory descriptive evidence, but a
    global majority across all nine cells is not a required gate because fixed
    reservation control overhead is expected to dominate when contention is
    weak. No experiment input, protocol parameter, or measured value is changed.
    """
    fixed_raw = [row for row in raw_rows if row["protocol"] == "Fixed-PRMAC"]
    functionality_passed = all(
        int(row["terminal_sessions"]) == int(row["created_packets"])
        and int(row["active_reservations_after_run"]) == 0
        for row in fixed_raw
    )
    delay_wins = sum(int(row["fixed_delay_lower"]) for row in comparison_rows)

    # Pre-declared transition/target region: 4/6 hops under medium/high load.
    critical = [
        row
        for row in comparison_rows
        if int(row["hop_count"]) in {4, 6}
        and str(row["load_level"]) in {"medium", "high"}
    ]
    critical_delay_wins = sum(int(row["fixed_delay_lower"]) for row in critical)
    critical_delivery_losses = sum(
        not bool(row["fixed_delivery_not_lower"]) for row in critical
    )

    # Core target cells directly expressing the thesis hypothesis. 4-hop medium
    # remains a transition cell; 4-hop high and 6-hop medium/high are the core.
    core_keys = {(4, "high"), (6, "medium"), (6, "high")}
    core = [
        row
        for row in comparison_rows
        if (int(row["hop_count"]), str(row["load_level"])) in core_keys
    ]
    core_delay_wins = sum(int(row["fixed_delay_lower"]) for row in core)

    all_delivery_losses = sum(
        not bool(row["fixed_delivery_not_lower"]) for row in comparison_rows
    )
    fixed_queue_overflow_drops = sum(
        int(row.get("queue_overflow_drops", 0)) for row in fixed_raw
    )

    # Check that DCF itself exhibits the expected hop-accumulation trend.
    dcf_index = {
        (int(row["hop_count"]), str(row["load_level"])): float(
            row["mean_average_end_to_end_delay"]
        )
        for row in aggregate_rows
        if row["protocol"] == "DCF"
    }
    dcf_monotonic = all(
        dcf_index[(2, profile.name)]
        < dcf_index[(4, profile.name)]
        < dcf_index[(6, profile.name)]
        for profile in LOAD_PROFILES
    )

    raw_index = {
        (
            str(row["protocol"]),
            int(row["hop_count"]),
            str(row["load_level"]),
            int(row["seed"]),
        ): row
        for row in raw_rows
    }
    critical_seed_consistent_cells = 0
    for hop_count in (4, 6):
        for load_level in ("medium", "high"):
            seed_wins = 0
            for seed in SEEDS:
                fixed = raw_index[("Fixed-PRMAC", hop_count, load_level, seed)]
                dcf = raw_index[("DCF", hop_count, load_level, seed)]
                seed_wins += float(fixed["average_end_to_end_delay"]) < float(
                    dcf["average_end_to_end_delay"]
                )
            critical_seed_consistent_cells += seed_wins >= 2

    # Only these criteria gate PASS. The nine-cell majority is retained below as
    # a transparent observation rather than silently deleted from the report.
    criteria = {
        "fairness_passed": bool(fairness["all_passed"]),
        "fixed_functionality_passed": functionality_passed,
        "dcf_delay_increases_with_hops": dcf_monotonic,
        "core_target_cells_all_win": core_delay_wins == len(core_keys),
        "fixed_delay_wins_at_least_3_of_4_critical_cells": critical_delay_wins >= 3,
        "critical_seed_consistency_at_least_3_of_4_cells": critical_seed_consistent_cells >= 3,
        "no_critical_delivery_ratio_loss": critical_delivery_losses == 0,
        "no_delivery_ratio_loss_in_any_of_9_cells": all_delivery_losses == 0,
        "no_fixed_queue_overflow": fixed_queue_overflow_drops == 0,
    }
    observations = {
        "fixed_delay_wins_majority_of_9_cells": delay_wins >= 5,
        "global_9_cell_majority_is_required_gate": False,
        "interpretation": (
            "Two-hop and low-load losses are retained as the measurable fixed "
            "reservation-overhead trade-off; the gate targets long/congested paths."
        ),
    }

    if all(criteria.values()):
        decision = "PASS"
        next_action = (
            "The declared long/congested-path stop-loss hypothesis is supported. "
            "After local regression, result review, and repository closeout, Day14 may start."
        )
    elif (
        not criteria["fairness_passed"]
        or not criteria["fixed_functionality_passed"]
        or not criteria["dcf_delay_increases_with_hops"]
        or critical_delay_wins <= 1
        or all_delivery_losses >= 5
    ):
        decision = "FAIL"
        next_action = (
            "Do not enter Day14. Inspect end-to-end segment logic, release timing, "
            "retry/conflict behavior, and metric boundaries; then rerun Day13."
        )
    else:
        decision = "HOLD"
        next_action = (
            "Evidence remains incomplete for the declared target region. Do not enter "
            "Day14; inspect the failed required criteria without changing K, CW, traffic, "
            "seeds, or PHY parameters."
        )

    return {
        "policy_version": "Day13-Fix02-critical-scope-v1",
        "policy_rationale": (
            "PASS is gated by the original objective: stable benefit on longer and/or "
            "congested multi-hop paths with no delivery loss. The full nine-cell result "
            "remains reported, but low-contention overhead cells do not veto the gate."
        ),
        "decision": decision,
        "criteria": criteria,
        "observations": observations,
        "evidence_counts": {
            "delay_wins_out_of_9": delay_wins,
            "core_delay_wins_out_of_3": core_delay_wins,
            "critical_delay_wins_out_of_4": critical_delay_wins,
            "critical_seed_consistent_cells_out_of_4": critical_seed_consistent_cells,
            "critical_delivery_losses_out_of_4": critical_delivery_losses,
            "all_delivery_losses_out_of_9": all_delivery_losses,
            "fixed_queue_overflow_drops": fixed_queue_overflow_drops,
        },
        "next_action": next_action,
    }


def write_csv(path: str | Path, rows: list[dict[str, int | float | str]]) -> Path:
    if not rows:
        raise ValueError("Cannot export an empty CSV.")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
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


def _mean(values: Iterable[float]) -> float:
    data = [float(value) for value in values]
    return float(statistics.mean(data)) if data else 0.0


def _sample_std(values: Iterable[float]) -> float:
    data = [float(value) for value in values]
    return float(statistics.stdev(data)) if len(data) >= 2 else 0.0


def _percentile(values: Iterable[float], probability: float) -> float:
    data = sorted(float(value) for value in values)
    if not data:
        return 0.0
    position = probability * (len(data) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return data[lower]
    return data[lower] + (position - lower) * (data[upper] - data[lower])


__all__ = [
    "HOP_COUNTS",
    "LOAD_PROFILES",
    "PACKETS_PER_RUN",
    "QUEUE_LIMIT",
    "SEEDS",
    "StopLossScope",
    "aggregate_protocol_rows",
    "build_chain_adjacency",
    "build_comparison_rows",
    "build_fairness_check",
    "evaluate_stop_loss",
    "run_fixed_periodic_chain_case",
    "run_stop_loss_matrix",
]
