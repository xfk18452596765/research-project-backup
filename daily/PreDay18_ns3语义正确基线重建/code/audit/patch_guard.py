from __future__ import annotations

import subprocess
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import REPO, STAGE, sha256_file, write_json


def main() -> int:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO,
        capture_output=True,
        check=True,
    )
    status = completed.stdout.decode("utf-8", errors="replace").splitlines()
    allowed = "daily/PreDay18_ns3"
    outside = [line for line in status if allowed not in line.replace("\\", "/")]
    patch = STAGE / "ns3" / "patches" / "ns3-3.43-fixed-prmac-access.patch"
    result = {
        "passed": not outside,
        "outside_stage_changes": outside,
        "patch_sha256": sha256_file(patch),
        "status": status,
    }
    write_json(STAGE / "results" / "audit" / "patch_guard.json", result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
