from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from analysis.decide_baseline_readiness import decide
from analysis.validate_causal_forwarding import validate as validate_causality
from analysis.validate_k2_lifecycle import validate as validate_k2, validate_retry
from analysis.validate_loss_accounting import validate as validate_loss
from analysis.validate_medium_effect import validate as validate_medium
from analysis.validate_topology import validate_calibration
from common import STAGE, load_json, read_trace, semantic_result_files, sha256_file, write_json

CLEAN_NS3_COMMIT = "753817468d611239b1e3c2e272b2bed8ef1f580c"
CLEAN_NS3_ARCHIVE_SHA256 = "da33eb5f3abb5e304ac8664f66ff117974be9811daa7cd340753e080902673fc"


def gate(passed: bool, evidence: Any) -> dict[str, Any]:
    return {"passed": bool(passed), "evidence": evidence}


def official_gate() -> dict[str, Any]:
    stdout = STAGE / "logs" / "gate0_official.stdout.log"
    text_report = STAGE / "logs" / "ns3_official_tests.txt"
    build_text = stdout.read_text(encoding="utf-8", errors="replace") if stdout.exists() else ""
    test_text = (
        text_report.read_text(encoding="utf-8", errors="replace")
        if text_report.exists()
        else ""
    )
    completed = "Finished executing the following commands:" in build_text
    passed = completed and "FAIL" not in test_text and "CRASH" not in test_text and bool(test_text)
    return gate(
        passed,
        {
            "full_build_completed": completed,
            "official_test_report": text_report.relative_to(STAGE).as_posix(),
            "failure_tokens_present": any(token in test_text for token in ("FAIL", "CRASH")),
        },
    )


def topology_gate() -> dict[str, Any]:
    stem = "calibration-dcf-6hop-1pkt-low-periodic-seed7"
    passed, issues = validate_calibration(
        read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl"),
        7,
        STAGE / "results" / "topology",
    )
    hidden_trace = read_trace(
        STAGE
        / "results"
        / "traces"
        / "hidden-fixed-1hop-5pkt-high-periodic-seed7.jsonl"
    )
    positions = [0.0, 30.0, 60.0]
    rss_matrix: list[list[float | None]] = []
    carrier_matrix: list[list[bool]] = []
    for source in range(3):
        rss_row: list[float | None] = []
        carrier_row: list[bool] = []
        for target in range(3):
            if source == target:
                rss_row.append(None)
                carrier_row.append(True)
            else:
                distance = abs(positions[source] - positions[target])
                rss = 22.0 - (46.6777 + 40.0 * math.log10(distance))
                rss_row.append(round(rss, 6))
                carrier_row.append(rss >= -93.0)
        rss_matrix.append(rss_row)
        carrier_matrix.append(carrier_row)
    collisions = [
        event for event in hidden_trace if event["event"] in ("PHY_RX_DROP", "MAC_RX_DROP")
    ]
    write_json(
        STAGE / "results" / "topology" / "hidden_terminal_topology.json",
        {
            "positions_m": {"A": [0, 0, 0], "B": [30, 0, 0], "C": [60, 0, 0]},
            "rss_dbm": rss_matrix,
            "carrier_sense": carrier_matrix,
            "A_C_mutual_carrier_sense": carrier_matrix[0][2],
            "A_to_B_decodable_by_threshold": rss_matrix[0][1] >= -85.0,
            "C_to_B_decodable_by_threshold": rss_matrix[2][1] >= -85.0,
            "collision_or_drop_events": len(collisions),
        },
    )
    collision_path = STAGE / "results" / "traces" / "hidden_terminal_collisions.jsonl"
    collision_path.write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in collisions),
        encoding="utf-8",
    )
    if carrier_matrix[0][2]:
        issues.append("hidden terminals A and C can carrier-sense one another")
    if rss_matrix[0][1] < -85.0 or rss_matrix[2][1] < -85.0:
        issues.append("hidden sender cannot reach B by frozen threshold")
    if not collisions:
        issues.append("hidden scenario produced no PHY/MAC drop evidence")
    return gate(not issues and passed, {"issues": issues, "hidden_drop_events": len(collisions)})


def dcf_gate() -> dict[str, Any]:
    issues: list[str] = []
    for hops in (1, 2, 4, 6):
        stem = f"chain-dcf-{hops}hop-1pkt-low-periodic-seed7"
        result = load_json(STAGE / "results" / "semantic" / f"{stem}.json")
        if result["delivered"] != 1:
            issues.append(f"{stem}: not delivered")
        passed, causal_issues = validate_causality(
            read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl"), hops
        )
        if not passed:
            issues.extend(f"{stem}: {item}" for item in causal_issues)
    low_results = [
        load_json(path)
        for path in semantic_result_files()
        if "chain-dcf-" in path.name and "10pkt-low" in path.name
    ]
    if len(low_results) != 18:
        issues.append(f"expected 18 DCF low-load cases, found {len(low_results)}")
    for result in low_results:
        if result["delivered"] != result["created"]:
            issues.append(
                f"DCF {result['hops']}hop seed{result['seed']}: incomplete delivery"
            )
    return gate(not issues, {"issues": issues, "low_load_cases": len(low_results)})


def k2_gate() -> dict[str, Any]:
    issues: list[str] = []
    for hops in (2, 4, 6):
        stem = f"chain-fixed-{hops}hop-1pkt-low-periodic-seed7"
        result = load_json(STAGE / "results" / "semantic" / f"{stem}.json")
        if result["delivered"] != 1:
            issues.append(f"{stem}: not delivered")
        passed, lifecycle_issues = validate_k2(
            read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl"), hops
        )
        if not passed:
            issues.extend(f"{stem}: {item}" for item in lifecycle_issues)
    retry_stem = "reservation-conflict-fixed-2hop-1pkt-low-periodic-seed7"
    retry_path = STAGE / "results" / "traces" / f"{retry_stem}.jsonl"
    if not retry_path.exists():
        issues.append("missing Fixed PR_NACK/BEB retry scenario")
    else:
        retry_passed, retry_issues = validate_retry(read_trace(retry_path))
        if not retry_passed:
            issues.extend(f"{retry_stem}: {item}" for item in retry_issues)
        retry_result = load_json(STAGE / "results" / "semantic" / f"{retry_stem}.json")
        if retry_result["delivered"] != 1:
            issues.append(f"{retry_stem}: retry did not deliver")
    return gate(not issues, {"issues": issues})


def medium_gate() -> dict[str, Any]:
    stem = "chain-fixed-6hop-1pkt-low-periodic-seed7"
    events = read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl")
    passed, issues = validate_medium(
        load_json(STAGE / "results" / "semantic" / f"{stem}.json"), events
    )
    multi = read_trace(
        STAGE
        / "results"
        / "traces"
        / "multiflow-m1-fixed-6hop-5pkt-low-periodic-seed7.jsonl"
    )
    grants = [event for event in multi if event["event"] == "DCF_ACCESS_GRANTED"]
    spatial_pairs = []
    for index, first in enumerate(grants):
        for second in grants[index + 1 : index + 60]:
            if (
                abs(first["node_id"] - second["node_id"]) >= 3
                and abs(first["time_us"] - second["time_us"]) <= 1000
            ):
                spatial_pairs.append(
                    {
                        "node_a": first["node_id"],
                        "time_a_us": first["time_us"],
                        "node_b": second["node_id"],
                        "time_b_us": second["time_us"],
                    }
                )
                break
        if len(spatial_pairs) >= 10:
            break
    if not spatial_pairs:
        issues.append("no distant-node reserved grants inside overlapping local windows")
    evidence = {
        "issues": issues,
        "spatial_reuse_pairs": spatial_pairs,
        "interpretation": "per-node Txop grants/blocks; no global channel lock",
    }
    write_json(STAGE / "results" / "semantic" / "medium_effect_evidence.json", evidence)
    return gate(passed and not issues, evidence)


def loss_gate() -> dict[str, Any]:
    issues: list[str] = []
    paths = list(semantic_result_files())
    for path in paths:
        passed, result_issues = validate_loss(load_json(path))
        if not passed:
            issues.extend(f"{path.name}: {item}" for item in result_issues)
    return gate(not issues and len(paths) >= 59, {"files": len(paths), "issues": issues})


def smoke_gate() -> dict[str, Any]:
    paths = [
        path
        for path in semantic_result_files()
        if ("10pkt-low" in path.name or "100pkt-high" in path.name)
    ]
    issues: list[str] = []
    if len(paths) != 48:
        issues.append(f"expected 48 smoke cases, found {len(paths)}")
    for path in paths:
        result = load_json(path)
        passed, result_issues = validate_loss(result)
        if not passed:
            issues.extend(f"{path.name}: {item}" for item in result_issues)
    return gate(not issues, {"cases": len(paths), "issues": issues})


def run_unit_tests() -> tuple[bool, str]:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            str(STAGE / "code" / "tests"),
            "-v",
        ],
        capture_output=True,
        check=False,
    )
    output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    output = output.replace("\r\n", "\n").replace("\r", "\n")
    (STAGE / "logs" / "stage_unit_tests.log").write_text(output, encoding="utf-8")
    return completed.returncode == 0, output


def source_hashes() -> dict[str, str]:
    patch = STAGE / "ns3" / "patches" / "ns3-3.43-fixed-prmac-access.patch"
    overlay = STAGE / "ns3" / "overlay" / "scratch" / "preday18-semantic-baseline.cc"
    patch_sha = sha256_file(patch)
    overlay_sha = sha256_file(overlay)
    combined = hashlib.sha256(
        (
            CLEAN_NS3_ARCHIVE_SHA256 + "\n" + patch_sha + "\n" + overlay_sha + "\n"
        ).encode("ascii")
    ).hexdigest()
    result = {
        "ns3_version": "3.43",
        "clean_commit": CLEAN_NS3_COMMIT,
        "clean_source_archive_sha256": CLEAN_NS3_ARCHIVE_SHA256,
        "patch_sha256": patch_sha,
        "overlay_sha256": overlay_sha,
        "patched_source_sha256": combined,
    }
    write_json(STAGE / "results" / "audit" / "source_hashes.json", result)
    return result


def main() -> int:
    unit_passed, unit_output = run_unit_tests()
    gates = {
        "Gate 0": official_gate(),
        "Gate 1": topology_gate(),
        "Gate 2": dcf_gate(),
        "Gate 3": k2_gate(),
        "Gate 4": medium_gate(),
        "Gate 5": loss_gate(),
        "Gate 6": smoke_gate(),
    }
    gates["Gate 0"]["evidence"]["repository_unit_tests_passed"] = unit_passed
    gates["Gate 0"]["passed"] = gates["Gate 0"]["passed"] and unit_passed
    outcome = decide(gates)
    outcome["source_hashes"] = source_hashes()
    regression_log = STAGE / "logs" / "day03_day17_regression.log"
    if regression_log.exists():
        regression_bytes = regression_log.read_bytes()
        if regression_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in regression_bytes[:200]:
            regression_text = regression_bytes.decode("utf-16", errors="replace")
        else:
            regression_text = regression_bytes.decode("utf-8", errors="replace")
    else:
        regression_text = ""
    outcome["Day03_Day17_regression"] = (
        "All Day03-Day17 regression tests passed." in regression_text
    )
    if not outcome["Day03_Day17_regression"]:
        outcome["baseline_decision"] = "BASELINE_HOLD"
    write_json(STAGE / "results" / "decision" / "baseline_readiness.json", outcome)

    lines = [
        f"baseline decision: {outcome['baseline_decision']}",
        *(f"{name}: {'PASS' if value['passed'] else 'HOLD'}" for name, value in gates.items()),
        f"Day03-Day17 regression: {'PASS' if outcome['Day03_Day17_regression'] else 'HOLD'}",
        "Day18 status: LOCKED",
        "stop-loss PASS rejudged: no",
        "RL run: no",
        "",
        unit_output,
    ]
    (STAGE / "test_results.txt").write_text("\n".join(lines), encoding="utf-8")
    print(outcome["baseline_decision"])
    return 0 if outcome["baseline_decision"] == "BASELINE_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
