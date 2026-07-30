from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import statistics
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from common import REPO, STAGE, load_json, sha256_file, write_json
from prepare_experiment_source import generate

WORKTREE = "/home/xfk/workspace/ns-3.43-fixed-prmac-baseline"
EXECUTABLE = f"{WORKTREE}/build/scratch/ns3.43-preday18-stop-loss-retest-default"
BASELINE = REPO / "daily" / "PreDay18_ns3语义正确基线重建"
SOURCE_HASHES = load_json(BASELINE / "results" / "audit" / "source_hashes.json")
FROZEN = load_json(STAGE / "configs" / "frozen_parameters.json")
CONTROL_TYPES = {"PR_REQ", "PR_ACK", "PR_NACK", "H_ACK", "RELEASE"}


@dataclass(frozen=True)
class Case:
    phase: str
    protocol: str
    scenario: str
    hops: int
    packets: int
    flows: int
    traffic: str
    load: str
    seed: int
    control_loss: float = 0.0

    @property
    def scenario_id(self) -> str:
        loss = f"-loss{self.control_loss:.2f}" if self.control_loss else ""
        return f"{self.phase}-{self.scenario}-{self.hops}hop-{self.load}-{self.traffic}-seed{self.seed}{loss}"

    @property
    def run_id(self) -> str:
        return f"{self.scenario_id}-{self.protocol}"


def wsl_path(path: Path) -> str:
    value = path.resolve()
    return f"/mnt/{value.drive[0].lower()}{value.as_posix().split(':', 1)[1]}"


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def parse_trace(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def enrich(case: Case, base: dict[str, Any], trace: list[dict[str, Any]], runtime: float) -> dict[str, Any]:
    created: dict[tuple[int, int], int] = {}
    delivered: dict[tuple[int, int], int] = {}
    frame_tx = []
    max_queue = 0
    for event in trace:
        key = (int(event["flow_id"]), int(event["packet_id"]))
        if event["event"] == "PACKET_CREATED":
            created[key] = int(event["time_us"])
        elif event["event"] == "PACKET_DELIVERED":
            delivered.setdefault(key, int(event["time_us"]))
        if event["event"].endswith("_TX") and event["frame_type"] in CONTROL_TYPES | {"DATA"}:
            frame_tx.append(event)
        max_queue = max(max_queue, int(event.get("queue_length", 0)))
    delays = [(delivered[key] - start) / 1e6 for key, start in created.items() if key in delivered]
    control_events = [event for event in frame_tx if event["frame_type"] in CONTROL_TYPES]
    data_events = [event for event in frame_tx if event["frame_type"] == "DATA"]
    control_bytes = sum(int(event.get("logical_size", 0)) for event in control_events)
    data_bytes = sum(int(event.get("logical_size", 0)) for event in data_events)
    first = min(created.values()) if created else 0
    last = max(delivered.values()) if delivered else first
    duration = max((last - first) / 1e6, 1e-9)
    per_flow = []
    for flow in range(case.flows):
        flow_created = sum(1 for key in created if key[0] == flow)
        flow_delivered = sum(1 for key in delivered if key[0] == flow)
        per_flow.append({"flow_id": flow, "created": flow_created, "delivered": flow_delivered, "delivery_ratio": flow_delivered / flow_created if flow_created else 0.0})
    flow_rates = [item["delivery_ratio"] for item in per_flow]
    jain = (sum(flow_rates) ** 2 / (len(flow_rates) * sum(x * x for x in flow_rates))) if flow_rates and any(flow_rates) else 0.0
    topology = base["topology"]
    topology_sha = canonical_sha({"scenario": case.scenario, **topology})
    config = {key: value for key, value in asdict(case).items() if key != "protocol"}
    config["frozen_parameters"] = FROZEN
    schedule = [{"flow": flow, "packet": packet, "time_us": timestamp} for (flow, packet), timestamp in sorted(created.items())]
    final_losses = int(base["created"]) - int(base["delivered"])
    simulation_end = max((int(e["time_us"]) for e in trace), default=0) / 1e6
    concurrent = 0
    tx_begins = [(int(e["time_us"]), int(e["node_id"])) for e in trace if e["event"] == "PHY_TX_BEGIN"]
    for index, (when, node) in enumerate(tx_begins):
        if any(other_node != node and abs(other_when - when) <= 1000 for other_when, other_node in tx_begins[index + 1:index + 30]):
            concurrent += 1
    return {
        "platform": "ns-3.43",
        "protocol": case.protocol,
        "scenario_id": case.scenario_id,
        "traffic": case.traffic,
        "topology": case.scenario,
        "hop_count": case.hops,
        "load": case.load,
        "seed": case.seed,
        "packet_count": int(base["created"]),
        "flow_count": case.flows,
        "created_packets": int(base["created"]),
        "delivered_packets": int(base["delivered"]),
        "delivery_ratio": int(base["delivered"]) / int(base["created"]) if base["created"] else 0.0,
        "average_e2e_delay": statistics.fmean(delays) if delays else 0.0,
        "p50_e2e_delay": percentile(delays, 0.50),
        "p95_e2e_delay": percentile(delays, 0.95),
        "p99_e2e_delay": percentile(delays, 0.99),
        "maximum_e2e_delay": max(delays, default=0.0),
        "throughput_bps": int(base["delivered"]) * FROZEN["payload_bytes"] * 8 / duration,
        "queue_overflow": int(base["terminal_counts"]["QUEUE_OVERFLOW"]),
        "maximum_queue_length": max_queue,
        "mac_retries": max(0, int(base["boundary_counters"]["mac_tx_drop"])),
        "phy_drops": int(base["boundary_counters"]["phy_rx_drop"]),
        "mac_drops": int(base["boundary_counters"]["mac_tx_drop"]) + int(base["boundary_counters"]["mac_rx_drop"]),
        "control_timeouts": int(base["terminal_counts"]["CONTROL_TIMEOUT"]) + int(base["terminal_counts"]["SEGMENT_DATA_TIMEOUT"]),
        "reservation_retries": sum(1 for e in trace if e["event"] == "DIFS_BEB_BACKOFF"),
        "control_frames": len(control_events),
        "control_bytes": control_bytes,
        "data_frames": len(data_events),
        "data_bytes": data_bytes,
        "control_airtime": control_bytes * 8 / 1_000_000,
        "data_airtime": data_bytes * 8 / 2_000_000,
        "simulation_end_time": simulation_end,
        "wall_clock_runtime": runtime,
        "active_reservations_after_run": int(base["active_reservations_after_run"]),
        "unknown_loss_count": int(base["unknown_loss"]),
        "final_loss_count": final_losses,
        "source_sha": SOURCE_HASHES["patched_source_sha256"],
        "patch_sha": SOURCE_HASHES["patch_sha256"],
        "experiment_source_sha": sha256_file(STAGE / "ns3" / "source" / "preday18-stop-loss-retest.cc"),
        "config_sha": canonical_sha(config),
        "traffic_schedule_sha": canonical_sha(schedule),
        "topology_sha": topology_sha,
        "per_flow": per_flow,
        "jain_fairness": jain,
        "concurrent_transmission_evidence_count": concurrent,
        "terminal_counts": base["terminal_counts"],
        "packets_detail": base["packets_detail"],
        "frozen_parameters": base["frozen_parameters"],
        "actual_load_interval_s": FROZEN["load_intervals_s"][case.load],
        "control_loss_probability": case.control_loss,
    }


def run_case(case: Case, root: Path) -> dict[str, Any]:
    raw_dir = root / "raw"
    trace_dir = root / "traces"
    log_dir = STAGE / "logs" / case.phase
    for directory in (raw_dir, trace_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    output = raw_dir / f"{case.run_id}.base.json"
    trace = trace_dir / f"{case.run_id}.jsonl"
    final = raw_dir / f"{case.run_id}.json"
    if final.exists():
        return load_json(final)
    args = [
        f"--protocol={case.protocol}", f"--scenario={case.scenario}", f"--hops={case.hops}",
        f"--packets={case.packets}", f"--flows={case.flows}", f"--traffic={case.traffic}",
        f"--load={case.load}", f"--seed={case.seed}", f"--controlLoss={case.control_loss}",
        f"--output={wsl_path(output)}", f"--trace={wsl_path(trace)}",
    ]
    command = " ".join([EXECUTABLE, *args])
    started = time.perf_counter()
    completed = subprocess.run(["wsl.exe", "bash", "-lc", command], cwd=REPO, capture_output=True, timeout=180, check=False)
    runtime = time.perf_counter() - started
    (log_dir / f"{case.run_id}.stdout.log").write_bytes(completed.stdout)
    (log_dir / f"{case.run_id}.stderr.log").write_bytes(completed.stderr)
    if completed.returncode or not output.exists() or not trace.exists():
        raise RuntimeError(f"{case.run_id} failed rc={completed.returncode}")
    enriched = enrich(case, load_json(output), parse_trace(trace), runtime)
    write_json(final, enriched)
    output.unlink()
    return enriched


def paired_integrity(results: list[dict[str, Any]]) -> list[str]:
    issues = []
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for result in results:
        groups.setdefault(result["scenario_id"], {})[result["protocol"]] = result
        if result["unknown_loss_count"] != 0 or result["active_reservations_after_run"] != 0:
            issues.append(f"{result['scenario_id']} {result['protocol']}: loss/reservation integrity")
        terminal_sum = sum(result["terminal_counts"].values())
        if terminal_sum != result["created_packets"] or result["created_packets"] != result["delivered_packets"] + result["final_loss_count"]:
            issues.append(f"{result['scenario_id']} {result['protocol']}: terminal accounting")
    for scenario, pair in groups.items():
        if set(pair) != {"dcf", "fixed"}:
            issues.append(f"{scenario}: incomplete pair")
            continue
        for key in ("traffic_schedule_sha", "topology_sha", "config_sha"):
            if pair["dcf"][key] != pair["fixed"][key]:
                issues.append(f"{scenario}: paired {key} mismatch")
    return issues


def execute(cases: list[Case], root: Path, workers: int = 6) -> list[dict[str, Any]]:
    results = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_case, case, root): case for case in cases}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            case = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append({"run_id": case.run_id, "error": str(exc)})
            if index % 20 == 0 or index == len(cases):
                print(f"{root.name}: {index}/{len(cases)} complete, failures={len(failures)}", flush=True)
    write_json(root / "aggregate" / "execution_summary.json", {"expected": len(cases), "completed": len(results), "failures": failures, "integrity_issues": paired_integrity(results)})
    if failures:
        raise RuntimeError(f"{len(failures)} runs failed")
    return results


def precheck_cases() -> list[Case]:
    return [Case("precheck", protocol, "chain", hops, 10, 1, traffic, "low", seed)
            for protocol in ("dcf", "fixed") for hops in (2, 4, 6)
            for traffic in ("periodic", "poisson") for seed in (7, 17, 27)]


def broad_cases() -> list[Case]:
    cfg = load_json(STAGE / "configs" / "broad_core_matrix.json")
    return [Case("broad_core", p, "chain", h, cfg["packets_per_run"], 1, t, load, seed)
            for p in cfg["protocols"] for h in cfg["hops"] for load in cfg["loads"]
            for t in cfg["traffic"] for seed in cfg["seeds"]]


def confirmatory_cases() -> list[Case]:
    cfg = load_json(STAGE / "configs" / "confirmatory_matrix.json")
    return [Case("confirmatory", p, "chain", cell["hops"], cfg["packets_per_run"], 1, t, cell["load"], seed)
            for p in cfg["protocols"] for cell in cfg["cells"] for t in cfg["traffic"] for seed in cfg["seeds"]]


def sensitivity_cases() -> list[Case]:
    cfg = load_json(STAGE / "configs" / "sensitivity_matrix.json")
    cases = []
    burst = cfg["burst"]
    cases += [Case("sensitivity_burst", p, "chain", h, burst["packets"], 1, "burst", "high", seed)
              for p in burst["protocols"] for h in burst["hops"] for seed in burst["seeds"]]
    multi = cfg["multiflow"]
    cases += [Case("sensitivity_multiflow", p, f"multiflow-{topology}", 6, multi["packets_per_flow"], 2, "periodic", load, seed)
              for p in multi["protocols"] for topology in multi["topologies"] for load in multi["loads"] for seed in multi["seeds"]]
    spatial = cfg["spatial_reuse"]
    cases += [Case("sensitivity_spatial", p, "spatial", 6, spatial["total_packets"] // 2, 2, "periodic", "high", seed)
              for p in spatial["protocols"] for seed in spatial["seeds"]]
    loss = cfg["control_loss"]
    cases += [Case("sensitivity_control_loss", p, "chain", 6, loss["packets"], 1, "poisson", "high", seed, probability)
              for p in loss["protocols"] for probability in loss["loss_probabilities"] for seed in loss["seeds"]]
    hidden = cfg["hidden_terminal"]
    cases += [Case("sensitivity_hidden", p, "hidden", 1, hidden["packets"] // 2, 2, "periodic", load, seed)
              for p in hidden["protocols"] for load in hidden["loads"] for seed in hidden["seeds"]]
    if len(cases) != cfg["expected_runs"]:
        raise RuntimeError(f"sensitivity matrix generated {len(cases)}, expected {cfg['expected_runs']}")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("precheck", "formal", "sensitivity", "all"), default="all")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    generate()
    if args.phase in ("precheck", "all"):
        results = execute(precheck_cases(), STAGE / "results" / "ns3" / "precheck", args.workers)
        issues = paired_integrity(results)
        if issues:
            write_json(STAGE / "results" / "decision" / "runtime_integrity_hold.json", {"decision": "HOLD", "reason": "BASELINE_RUNTIME_INTEGRITY_FAILURE", "issues": issues})
            return 2
    if args.phase in ("formal", "all"):
        execute(broad_cases(), STAGE / "results" / "ns3" / "broad_core", args.workers)
        execute(confirmatory_cases(), STAGE / "results" / "ns3" / "confirmatory", args.workers)
    if args.phase in ("sensitivity", "all"):
        execute(sensitivity_cases(), STAGE / "results" / "ns3" / "sensitivity", args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
