from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone

from common import HISTORICAL, REPO, STAGE, directory_manifest, load_json, sha256_file, write_json

EXPECTED_HEAD = "38cd5b7aa05556f00aaa6169aa34d805bccc1a3a"
BASELINE = REPO / "daily" / "PreDay18_ns3语义正确基线重建"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True, encoding="utf-8").strip()


def git_blob_sha256(relative: str) -> str:
    payload = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=REPO)
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    failures = []
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    status = git("status", "--short")
    if head != EXPECTED_HEAD:
        failures.append(f"HEAD {head} != {EXPECTED_HEAD}")
    if branch != "main":
        failures.append(f"branch {branch} != main")
    allowed_prefix = "daily/PreDay18_语义正确基线止损复验/"
    unexpected = [line for line in status.splitlines() if allowed_prefix not in line.replace("\\", "/")]
    if unexpected:
        failures.append(f"unexpected working-tree changes: {unexpected}")

    decision = load_json(BASELINE / "results" / "decision" / "baseline_readiness.json")
    source_hashes = load_json(BASELINE / "results" / "audit" / "source_hashes.json")
    if decision.get("baseline_decision") != "BASELINE_READY":
        failures.append("baseline decision is not BASELINE_READY")
    failed_gates = [name for name, value in decision.get("gates", {}).items() if not value.get("passed")]
    if failed_gates or len(decision.get("gates", {})) != 7:
        failures.append(f"baseline gates invalid: {failed_gates}")
    if not decision.get("Day03_Day17_regression"):
        failures.append("baseline Day03-Day17 regression not passed")
    if decision.get("RL_run"):
        failures.append("baseline reports RL run")
    if decision.get("source_hashes") != source_hashes:
        failures.append("baseline source hash records disagree")
    patch_relative = "daily/PreDay18_ns3语义正确基线重建/ns3/patches/ns3-3.43-fixed-prmac-access.patch"
    overlay_relative = "daily/PreDay18_ns3语义正确基线重建/ns3/overlay/scratch/preday18-semantic-baseline.cc"
    actual_patch = git_blob_sha256(patch_relative)
    if actual_patch != source_hashes["patch_sha256"]:
        failures.append("baseline patch SHA mismatch")
    if git_blob_sha256(overlay_relative) != source_hashes["overlay_sha256"]:
        failures.append("baseline overlay SHA mismatch")

    manifests = [directory_manifest(path) for path in HISTORICAL]
    policy_path = STAGE / "configs" / "stop_loss_policy.json"
    policy_sha = sha256_file(policy_path)
    audit = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": head,
        "branch": branch,
        "baseline_verified": not failures,
        "baseline_decision": decision.get("baseline_decision"),
        "gates": {k: v.get("passed") for k, v in decision.get("gates", {}).items()},
        "source_hashes": source_hashes,
        "hashing_note": "Tracked source artifacts are verified from canonical Git blobs; Windows checkout CRLF conversion changes raw worktree byte hashes.",
        "configuration_sha256": sha256_file(BASELINE / "configs" / "frozen_parameters.json"),
        "semantic_baseline_source_sha256": source_hashes["patched_source_sha256"],
        "failures": failures,
    }
    write_json(STAGE / "results" / "audit" / "baseline_input_verification.json", audit)
    write_json(STAGE / "results" / "audit" / "historical_evidence_start.json", {"manifests": manifests})
    write_json(STAGE / "results" / "audit" / "stop_loss_policy_sha256.json", {"path": policy_path.relative_to(STAGE).as_posix(), "sha256": policy_sha})
    print(json.dumps({"baseline_verified": not failures, "policy_sha256": policy_sha, "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
