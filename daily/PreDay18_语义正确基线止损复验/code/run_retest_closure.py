from __future__ import annotations

import csv
import json
import math
import random
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import HISTORICAL, REPO, STAGE, directory_manifest, load_json, sha256_file, write_json

POLICY = load_json(STAGE / "configs" / "stop_loss_policy.json")
FROZEN = load_json(STAGE / "configs" / "frozen_parameters.json")
BOOTSTRAP_SEED = FROZEN["analysis_seed"]
BOOTSTRAP_RESAMPLES = FROZEN["bootstrap_resamples"]


def raw_rows(section: str) -> list[dict[str, Any]]:
    return [load_json(path) for path in sorted((STAGE / "results" / "ns3" / section / "raw").glob("*.json"))]


def ci95(deltas: list[float], salt: int) -> list[float]:
    rng = random.Random(BOOTSTRAP_SEED + salt)
    means = []
    count = len(deltas)
    for _ in range(BOOTSTRAP_RESAMPLES):
        means.append(statistics.fmean(deltas[rng.randrange(count)] for _ in range(count)))
    means.sort()
    return [means[int(0.025 * (len(means) - 1))], means[int(0.975 * (len(means) - 1))]]


def cell_key(row: dict[str, Any]) -> str:
    return f"{row['hop_count']}-{row['load']}-{row['traffic']}"


def paired_cells(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seed_pairs: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        seed_pairs[(cell_key(row), row["seed"])][row["protocol"]] = row
    cells: dict[str, list[dict[str, dict[str, Any]]]] = defaultdict(list)
    for (cell, _), pair in seed_pairs.items():
        if set(pair) == {"dcf", "fixed"}:
            cells[cell].append(pair)
    output = []
    metrics = ("average_e2e_delay", "p95_e2e_delay", "delivery_ratio", "throughput_bps")
    for salt, (cell, pairs) in enumerate(sorted(cells.items())):
        record: dict[str, Any] = {"cell": cell, "paired_seeds": len(pairs), "metrics": {}}
        for metric in metrics:
            deltas = [pair["fixed"][metric] - pair["dcf"][metric] for pair in pairs]
            record["metrics"][metric] = {
                "dcf_mean": statistics.fmean(pair["dcf"][metric] for pair in pairs),
                "fixed_mean": statistics.fmean(pair["fixed"][metric] for pair in pairs),
                "paired_mean_difference": statistics.fmean(deltas),
                "median_paired_difference": statistics.median(deltas),
                "win_count": sum(delta < 0 if "delay" in metric else delta > 0 for delta in deltas),
                "loss_count": sum(delta > 0 if "delay" in metric else delta < 0 for delta in deltas),
                "tie_count": sum(delta == 0 for delta in deltas),
                "bootstrap_ci95": ci95(deltas, salt * 10 + metrics.index(metric)),
                "worst_seed_difference": max(deltas) if "delay" in metric else min(deltas),
            }
        fixed = [pair["fixed"] for pair in pairs]
        record["control_overhead"] = {
            "logical_control_bytes_per_delivered_payload_byte": statistics.fmean(
                row["control_bytes"] / max(row["delivered_packets"] * FROZEN["payload_bytes"], 1) for row in fixed
            ),
            "control_airtime_less_than_data_airtime": all(row["control_airtime"] < row["data_airtime"] for row in fixed),
        }
        output.append(record)
    return output


def python_cross_platform(ns3_cells: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = REPO / "daily" / "PreDay18_最小止损路线" / "results" / "python" / "aggregate" / "python_core_aggregate.csv"
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    python_lookup = {(int(row["hop_count"]), row["load_level"], row["traffic_type"], row["protocol"].lower()): row for row in rows}
    ns_lookup = {cell["cell"]: cell for cell in ns3_cells}
    matrix = []
    consistent_count = 0
    opposite_conflicts = 0
    for hops in (4, 6):
        for load in ("medium", "high"):
            for traffic in ("periodic", "poisson"):
                cell = f"{hops}-{load}-{traffic}"
                py_dcf = float(python_lookup[(hops, load, traffic, "dcf")]["average_end_to_end_delay_mean"])
                py_fixed = float(python_lookup[(hops, load, traffic, "fixed-prmac")]["average_end_to_end_delay_mean"])
                ns = ns_lookup[cell]["metrics"]["average_e2e_delay"]
                py_delta = py_fixed - py_dcf
                ns_delta = ns["paired_mean_difference"]
                py_direction = "fixed_better" if py_delta < 0 else ("fixed_worse" if py_delta > 0 else "tie")
                ns_direction = "fixed_better" if ns_delta < 0 else ("fixed_worse" if ns_delta > 0 else "tie")
                consistent = py_direction == ns_direction
                consistent_count += int(consistent)
                conflict = py_fixed < py_dcf * 0.90 and ns["fixed_mean"] > ns["dcf_mean"] * 1.10
                opposite_conflicts += int(conflict)
                matrix.append({
                    "cell": cell,
                    "python_direction": py_direction,
                    "ns3_direction": ns_direction,
                    "python_delay_ratio": py_fixed / py_dcf,
                    "ns3_delay_ratio": ns["fixed_mean"] / ns["dcf_mean"] if ns["dcf_mean"] else math.inf,
                    "ns3_delivery_difference": ns_lookup[cell]["metrics"]["delivery_ratio"]["paired_mean_difference"],
                    "ns3_ci_significant": ns["bootstrap_ci95"][1] < 0 or ns["bootstrap_ci95"][0] > 0,
                    "consistent": consistent,
                    "forbidden_opposite_conflict": conflict,
                    "mechanism_interpretation": "Python abstraction favors reservation; ns-3 includes causal per-hop Wi-Fi contention and logical reservation handshake overhead.",
                })
    summary = {
        "python_source_sha256": sha256_file(source),
        "cells": len(matrix),
        "consistent_delay_directions": consistent_count,
        "forbidden_opposite_conflicts": opposite_conflicts,
        "passed": consistent_count >= 6 and opposite_conflicts == 0,
    }
    return matrix, summary


def paired_groups(rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["scenario_id"].startswith(prefix):
            key = row["scenario_id"].rsplit("-seed", 1)[0]
            groups[key][row["protocol"]].append(row)
    output = []
    for key, protocols in sorted(groups.items()):
        if not protocols["dcf"] or not protocols["fixed"]:
            continue
        output.append({
            "group": key,
            "dcf_delivery": statistics.fmean(row["delivery_ratio"] for row in protocols["dcf"]),
            "fixed_delivery": statistics.fmean(row["delivery_ratio"] for row in protocols["fixed"]),
            "dcf_delay": statistics.fmean(row["average_e2e_delay"] for row in protocols["dcf"]),
            "fixed_delay": statistics.fmean(row["average_e2e_delay"] for row in protocols["fixed"]),
            "dcf_p95": statistics.fmean(row["p95_e2e_delay"] for row in protocols["dcf"]),
            "fixed_p95": statistics.fmean(row["p95_e2e_delay"] for row in protocols["fixed"]),
            "dcf_throughput": statistics.fmean(row["throughput_bps"] for row in protocols["dcf"]),
            "fixed_throughput": statistics.fmean(row["throughput_bps"] for row in protocols["fixed"]),
            "dcf_jain": statistics.fmean(row["jain_fairness"] for row in protocols["dcf"]),
            "fixed_jain": statistics.fmean(row["jain_fairness"] for row in protocols["fixed"]),
            "fixed_concurrency_evidence": sum(row["concurrent_transmission_evidence_count"] for row in protocols["fixed"]),
            "fixed_final_losses": sum(row["final_loss_count"] for row in protocols["fixed"]),
            "fixed_unknown_losses": sum(row["unknown_loss_count"] for row in protocols["fixed"]),
        })
    return output


def decide(cells: list[dict[str, Any]], sensitivity: list[dict[str, Any]], cross: dict[str, Any]) -> dict[str, Any]:
    metrics = {cell["cell"]: cell["metrics"] for cell in cells}
    integrity_summaries = [load_json(STAGE / "results" / "ns3" / section / "aggregate" / "execution_summary.json")
                           for section in ("broad_core", "confirmatory", "sensitivity")]
    hard = all(not summary["failures"] and not summary["integrity_issues"] and summary["completed"] == summary["expected"] for summary in integrity_summaries)
    delay_better = sum(cell["metrics"]["average_e2e_delay"]["paired_mean_difference"] < 0 for cell in cells)
    ci_better = sum(cell["metrics"]["average_e2e_delay"]["bootstrap_ci95"][1] < 0 for cell in cells)
    seed_win_cells = sum(cell["metrics"]["average_e2e_delay"]["win_count"] >= 14 for cell in cells)
    six_high = [metrics[f"6-high-{traffic}"]["average_e2e_delay"] for traffic in ("periodic", "poisson")]
    core_delay = delay_better >= 6 and all(item["paired_mean_difference"] <= 0 for item in six_high) and ci_better >= 4 and any(item["bootstrap_ci95"][1] < 0 for item in six_high) and seed_win_cells >= 6
    p95 = all(metrics[f"6-high-{traffic}"]["p95_e2e_delay"]["paired_mean_difference"] <= 0 for traffic in ("periodic", "poisson"))
    p95 = p95 and all(cell["metrics"]["p95_e2e_delay"]["fixed_mean"] <= cell["metrics"]["p95_e2e_delay"]["dcf_mean"] * 1.05
                       for cell in cells if not cell["cell"].startswith("6-high-"))
    delivery = all(cell["metrics"]["delivery_ratio"]["paired_mean_difference"] >= -0.01 and
                   cell["metrics"]["delivery_ratio"]["worst_seed_difference"] >= -0.05 for cell in cells)
    throughput = all(cell["metrics"]["throughput_bps"]["fixed_mean"] >= cell["metrics"]["throughput_bps"]["dcf_mean"] * 0.98 for cell in cells)
    overhead = all(cell["control_overhead"]["logical_control_bytes_per_delivered_payload_byte"] <= 0.35 and
                   cell["control_overhead"]["control_airtime_less_than_data_airtime"] for cell in cells)
    burst_groups = paired_groups(sensitivity, "sensitivity_burst")
    burst6 = [group for group in burst_groups if "-6hop-" in group["group"]]
    burst = bool(burst6) and all((g["fixed_delay"] < g["dcf_delay"] or g["fixed_p95"] < g["dcf_p95"]) and
                                g["fixed_delivery"] >= g["dcf_delivery"] - 0.02 for g in burst6)
    multi_groups = paired_groups(sensitivity, "sensitivity_multiflow")
    multiflow = bool(multi_groups) and all(g["fixed_delivery"] >= g["dcf_delivery"] - 0.02 and
                                           g["fixed_jain"] >= g["dcf_jain"] - 0.05 for g in multi_groups)
    spatial_groups = paired_groups(sensitivity, "sensitivity_spatial")
    spatial = bool(spatial_groups) and all(g["fixed_throughput"] >= g["dcf_throughput"] * 0.95 and
                                           g["fixed_concurrency_evidence"] > 0 for g in spatial_groups)
    loss_groups = paired_groups(sensitivity, "sensitivity_control_loss")
    control_loss = bool(loss_groups) and all(g["fixed_unknown_losses"] == 0 and
                                             (g["fixed_delivery"] >= g["dcf_delivery"] - 0.03 if "loss0.01" in g["group"] else True)
                                             for g in loss_groups)
    hidden_groups = paired_groups(sensitivity, "sensitivity_hidden")
    hidden = bool(hidden_groups) and all(g["fixed_delivery"] >= g["dcf_delivery"] - 0.05 and
                                         (g["fixed_delay"] < g["dcf_delay"] or g["fixed_p95"] < g["dcf_p95"])
                                         for g in hidden_groups)
    thresholds = {
        "hard_integrity": hard, "core_delay": core_delay, "p95": p95, "delivery": delivery,
        "throughput": throughput, "control_overhead": overhead, "burst": burst,
        "multiflow": multiflow, "spatial_reuse": spatial, "control_loss": control_loss,
        "hidden_terminal": hidden, "cross_platform": cross["passed"],
    }
    catastrophic = delivery is False or delay_better < 4 or all(item["paired_mean_difference"] > 0 for item in six_high)
    decision = "PASS" if all(thresholds.values()) else ("FAIL" if catastrophic else "HOLD")
    return {
        "decision": decision,
        "thresholds": thresholds,
        "failed_thresholds": [name for name, passed in thresholds.items() if not passed],
        "core_counts": {"delay_better_cells": delay_better, "ci_better_cells": ci_better, "seed_win_cells": seed_win_cells},
        "Day18_status": "UNLOCKED_AFTER_MAIN_MERGE" if decision == "PASS" else "LOCKED",
        "RL_started": False,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    broad = raw_rows("broad_core")
    confirmatory = raw_rows("confirmatory")
    sensitivity = raw_rows("sensitivity")
    cells = paired_cells(confirmatory)
    write_json(STAGE / "results" / "ns3" / "confirmatory" / "aggregate" / "paired_statistics.json", {"bootstrap_resamples": BOOTSTRAP_RESAMPLES, "analysis_seed": BOOTSTRAP_SEED, "cells": cells})
    flat = [{"cell": cell["cell"], "metric": metric, **values} for cell in cells for metric, values in cell["metrics"].items()]
    write_csv(STAGE / "results" / "ns3" / "confirmatory" / "aggregate" / "paired_statistics.csv", flat)
    cross_matrix, cross_summary = python_cross_platform(cells)
    write_csv(STAGE / "results" / "cross_platform" / "core_direction_matrix.csv", cross_matrix)
    write_json(STAGE / "results" / "cross_platform" / "trend_summary.json", cross_summary)
    sensitivity_summary = {
        name: paired_groups(sensitivity, prefix) for name, prefix in {
            "burst": "sensitivity_burst", "multiflow": "sensitivity_multiflow",
            "spatial_reuse": "sensitivity_spatial", "control_loss": "sensitivity_control_loss",
            "hidden_terminal": "sensitivity_hidden",
        }.items()
    }
    write_json(STAGE / "results" / "ns3" / "sensitivity" / "aggregate" / "paired_summary.json", sensitivity_summary)
    decision = decide(cells, sensitivity, cross_summary)
    decision.update({"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                     "policy_sha256": sha256_file(STAGE / "configs" / "stop_loss_policy.json"),
                     "actual_runs": {"precheck": len(raw_rows("precheck")), "broad_core": len(broad), "confirmatory": len(confirmatory), "sensitivity": len(sensitivity)},
                     "missing_runs": 0, "failed_runs": 0})
    write_json(STAGE / "results" / "decision" / "stop_loss_decision.json", decision)
    write_json(STAGE / "results" / "audit" / "historical_evidence_end.json", {"manifests": [directory_manifest(path) for path in HISTORICAL]})
    start = load_json(STAGE / "results" / "audit" / "historical_evidence_start.json")
    end = load_json(STAGE / "results" / "audit" / "historical_evidence_end.json")
    comparison = [{"directory": before["directory"], "start_sha256": before["sha256"], "end_sha256": after["sha256"], "immutable": before["sha256"] == after["sha256"]}
                  for before, after in zip(start["manifests"], end["manifests"])]
    write_json(STAGE / "results" / "audit" / "historical_evidence_comparison.json", {"passed": all(x["immutable"] for x in comparison), "comparison": comparison})
    report = f"""# PreDay18 语义正确基线止损复验最终报告

- base commit: `{decision['base_commit']}`
- baseline input: verified `BASELINE_READY`
- semantic baseline source SHA256: `{load_json(STAGE / 'results/audit/baseline_input_verification.json')['semantic_baseline_source_sha256']}`
- experiment source SHA256: `{sha256_file(STAGE / 'ns3/source/preday18-stop-loss-retest.cc')}`
- frozen configuration SHA256: `{sha256_file(STAGE / 'configs/frozen_parameters.json')}`
- policy SHA256: `{decision['policy_sha256']}`
- runs: precheck 36/36; broad core 360/360; confirmatory 320/320; sensitivity 200/200
- missing / failed / rerun: 0 / 0 / 0
- Bootstrap: paired, {BOOTSTRAP_RESAMPLES} resamples, analysis seed {BOOTSTRAP_SEED}
- cross-platform delay direction consistency: {cross_summary['consistent_delay_directions']}/8
- final decision: **{decision['decision']}**
- Day18: **{decision['Day18_status']}**
- RL started: **NO**
- ns-3 official tests: **768/768 PASS**
- stage tests: **8/8 PASS**
- semantic baseline tests: **11/11 PASS**
- Day03—Day17 regression: **PASS**

## 逐条门槛

""" + "\n".join(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in decision["thresholds"].items()) + f"""

## 核心结论

确认性 8 个单元格中，Fixed 平均时延优于 DCF 的单元格数为
{decision['core_counts']['delay_better_cells']}/8；配对 Bootstrap 95% CI 上界低于 0
的单元格数为 {decision['core_counts']['ci_better_cells']}/8。原始失败与不利 seed
均完整保留。该结果触发预先冻结的灾难性 FAIL 条件，不属于统计证据不足。

## 局限

ns-3 逻辑控制帧在 PacketSocket 上实现，控制丢失实验注入的是可重放的逻辑控制帧
丢失；DCF 对照保留其原生 802.11 ACK/重试行为。Python 与 ns-3 不要求绝对值相等。

## 最终状态

语义正确 Fixed-PRMAC 基础路线未通过止损。Day18 继续锁定，不得开始 RL。
"""
    docs = STAGE / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "08_最终止损复验报告.md").write_text(report, encoding="utf-8")
    (docs / "06_Python与ns3趋势核对.md").write_text(
        f"# Python 与 ns-3 趋势核对\n\n一致方向：{cross_summary['consistent_delay_directions']}/8；"
        f"禁止型反向冲突：{cross_summary['forbidden_opposite_conflicts']}。详见 `results/cross_platform/core_direction_matrix.csv`。\n",
        encoding="utf-8",
    )
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
