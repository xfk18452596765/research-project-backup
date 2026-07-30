from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "code"))
from audit.evidence import collect_manifest  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = ROOT / "results" / "audit" / "original_evidence_sha256.json"
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert collect_manifest() == expected

    source = ROOT / "ns3" / "scratch" / "preday18-diagnostic-reference.cc"
    text = source.read_text(encoding="utf-8")
    for token in ("CW_MIN = 15", "CW_MAX = 1023", "RETRY_LIMIT = 7", "SLOT_US = 20", "K = 2"):
        assert token in text

    outputs = sorted((ROOT / "results" / "diagnostic_runs").glob("*.json"))
    traces = sorted((ROOT / "results" / "traces").glob("*.jsonl"))
    assert len(outputs) == 188
    assert len(traces) == 188
    for output in outputs:
        row = json.loads(output.read_text(encoding="utf-8"))
        assert row["created"] == sum(row["terminal_counts"].values())
        assert row["unknown_loss"] == 0
        assert len(row["packets_detail"]) == row["created"]
        assert len({x["seq"] for x in row["packets_detail"]}) == row["created"]
        if row["k2_segment"] and row["protocol"] == "fixed":
            assert max(x["max_segment_hops"] for x in row["packets_detail"]) <= 2
        if row["causal_forwarding"]:
            events = [json.loads(line) for line in (
                ROOT / "results" / "traces" / output.with_suffix(".jsonl").name
            ).read_text(encoding="utf-8").splitlines()]
            for seq in range(row["created"]):
                packet = [x for x in events if x["seq"] == seq]
                for hop in range(1, row["hops"]):
                    enqueue = [x["time_us"] for x in packet if x["hop"] == hop and x["event"] == "MAC_ENQUEUE"]
                    previous_rx = [x["time_us"] for x in packet if x["hop"] == hop - 1 and x["event"] == "UDP_RX"]
                    if enqueue:
                        assert previous_rx and min(enqueue) > max(previous_rx)

    repro = ROOT / "results" / "audit" / "reproducibility"
    result_a, result_b = repro / "result-a.json", repro / "result-b.json"
    trace_a, trace_b = repro / "trace-a.jsonl", repro / "trace-b.jsonl"
    assert result_a.exists() and result_b.exists() and trace_a.exists() and trace_b.exists()
    assert sha(result_a) == sha(result_b)
    assert sha(trace_a) == sha(trace_b)
    assert json.loads(result_a.read_text(encoding="utf-8"))["seed"] == 7

    decision = json.loads((ROOT / "results" / "decision" / "root_cause_classification.json").read_text(encoding="utf-8"))
    assert decision["preday18_decision"] == "FAIL (unchanged)"
    assert decision["day18_status"] == "LOCKED"
    assert decision["rl_training"] == "NOT_RUN"
    assert decision["root_cause_classification"] in {
        "IMPLEMENTATION_ARTIFACT_CONFIRMED",
        "PROTOCOL_MECHANISM_FAILURE_CONFIRMED",
        "MIXED_ROOT_CAUSE",
        "INCONCLUSIVE",
    }
    print("Diagnostic tests passed: immutable evidence, causal chain, K=2, unique terminals, UNKNOWN_LOSS=0, reproducibility, UTF-8 JSON")


if __name__ == "__main__":
    main()
