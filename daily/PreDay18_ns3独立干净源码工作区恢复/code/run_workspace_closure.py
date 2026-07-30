#!/usr/bin/env python3
"""Fail-closed audit entry point for the ns-3.43 workspace recovery task."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parents[1]
OUT = STAGE / "results" / "manifests"
AUDIT = STAGE / "results" / "audit"

PATCHES = {
    "semantic": {
        "path": ROOT / "daily" / "PreDay18_ns3语义正确基线重建" / "ns3" / "patches" / "ns3-3.43-fixed-prmac-access.patch",
        "expected": "90823ff0d2bc380ad838007293b87c87f3631c73b313b38b92d4da46907184db",
    },
    "attribution": {
        "path": ROOT / "daily" / "PreDay18_Fixed-PRMAC归因Trace补全" / "ns3" / "patches" / "attribution-trace-completion.patch",
        "expected": "9405e0e83684725e92bcd0bf99c8f567f6d17a1f8501468b0c4ca1bd91ca43d1",
    },
    "lifecycle": {
        "path": ROOT / "daily" / "PreDay18_Fixed-PRMAC生命周期Trace闭合" / "ns3" / "patches" / "lifecycle-trace-completion.patch",
        "expected": "8c55571e688502973dfbde0eb0a3dd0289354a55c8550efbd3995f9c6195ab46",
    },
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    observed = {name: {"path": str(item["path"].relative_to(ROOT)), "expected_sha256": item["expected"],
                       "actual_sha256": sha256(item["path"]), "match": sha256(item["path"]) == item["expected"]}
                for name, item in PATCHES.items()}
    mismatches = [name for name, value in observed.items() if not value["match"]]
    evidence = {
        "base_commit": git("rev-parse", "33338ef"),
        "head_commit": git("rev-parse", "HEAD"),
        "historical_paths_modified": git("diff", "--name-only", "33338ef", "--", "daily/Day*", "daily/PreDay18_*").splitlines(),
        "patches": observed,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "result": "PASS" if not mismatches else "FAIL",
    }
    decision = "NS3_WORKSPACE_READY" if not mismatches else "NS3_WORKSPACE_HOLD"
    manifest = {
        "decision": decision,
        "reason": None if not mismatches else "PATCH_SHA_MISMATCH",
        "blocked_before": ["clean-source recovery", "patch dry-run/apply", "configure", "build", "official tests", "lifecycle binary", "smoke", "rebuild verification"],
        "formal_lifecycle_runs_executed": False,
        "day18_status": "LOCKED",
        "rl_started": False,
        "workspace_path": "~/workspace/ns-3.43-lifecycle-trace-clean (not created; fail-closed)",
        "patches": observed,
    }
    (AUDIT / "historical_evidence_audit.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    (OUT / "patch_chain_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT / "clean_source_manifest.json").write_text(json.dumps({"status": "NOT_CREATED", "reason": manifest["reason"]}, indent=2) + "\n", encoding="utf-8")
    print(decision)
    return 0 if decision == "NS3_WORKSPACE_READY" else 2

if __name__ == "__main__":
    raise SystemExit(main())
