from __future__ import annotations

import argparse
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import REPO, STAGE, evidence_manifest, load_json, write_json

HISTORICAL = (
    REPO / "daily" / "PreDay18_最小止损路线",
    REPO / "daily" / "PreDay18_Fixed-PRMAC机制诊断",
)


def capture(label: str) -> dict:
    result = {"label": label, "directories": [evidence_manifest(p) for p in HISTORICAL]}
    write_json(STAGE / "results" / "audit" / f"historical_evidence_{label}.json", result)
    return result


def compare() -> bool:
    start = load_json(STAGE / "results" / "audit" / "historical_evidence_start.json")
    end = load_json(STAGE / "results" / "audit" / "historical_evidence_end.json")
    comparison = []
    for before, after in zip(start["directories"], end["directories"], strict=True):
        comparison.append(
            {
                "directory": before["directory"],
                "start_sha256": before["manifest_sha256"],
                "end_sha256": after["manifest_sha256"],
                "file_count_start": before["file_count"],
                "file_count_end": after["file_count"],
                "immutable": before["manifest_sha256"] == after["manifest_sha256"],
            }
        )
    passed = all(item["immutable"] for item in comparison)
    write_json(
        STAGE / "results" / "audit" / "historical_evidence_comparison.json",
        {"passed": passed, "comparison": comparison},
    )
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "end", "compare"))
    args = parser.parse_args()
    if args.action in ("start", "end"):
        capture(args.action)
        raise SystemExit(0)
    raise SystemExit(0 if compare() else 1)
