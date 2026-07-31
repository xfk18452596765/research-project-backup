#!/usr/bin/env python3
"""Fail-closed V2 evidence audit; it never fabricates simulator results."""
from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
REPO = STAGE.parents[1]
OUT = STAGE / "results" / "audit"

def digest_tree(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        h.update(p.relative_to(root).as_posix().encode()); h.update(b"\\0")
        h.update(oct(p.stat().st_mode & 0o777).encode()); h.update(b"\\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain"], cwd=REPO,
                               text=True, encoding="utf-8", errors="replace", capture_output=True, check=True)
    status = completed.stdout.splitlines()
    forbidden = [x for x in status if not x[3:].replace("\\", "/").startswith("daily/PreDay18_ns3语义基线重新版本化重建/")]
    historical = [p for p in (REPO / "daily").iterdir() if p.name != STAGE.name]
    identity = json.loads((STAGE / "configs" / "baseline_v2_identity.json").read_text(encoding="utf-8"))
    report = {
      "historical_results_retained": True,
      "historical_patch_chain_reproducibility": "incomplete",
      "historical_P1_authority": "unavailable",
      "v2_identity": identity,
      "stage_tree_sha256": digest_tree(STAGE),
      "historical_directories_present": len(historical),
      "out_of_scope_changes": forbidden,
      "decision": "SEMANTIC_BASELINE_V2_HOLD",
      "hold_reason": "IMPLEMENTATION_AND_EMPIRICAL_EVIDENCE_NOT_YET_COMPLETE",
      "ready_guard": "A READY decision requires real official-source A/B execution and Gates 0-7 evidence."
    }
    (OUT / "audit.json").write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if not forbidden else 2
if __name__ == "__main__": raise SystemExit(main())
