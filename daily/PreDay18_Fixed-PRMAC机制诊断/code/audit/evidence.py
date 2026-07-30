from __future__ import annotations

import hashlib
import json
from pathlib import Path

DIAG_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = DIAG_ROOT.parents[1]
HISTORY = REPO_ROOT / "daily" / "PreDay18_最小止损路线"
TARGETS = [
    HISTORY / "ns3" / "scratch" / "preday18-dcf-fixed-prmac.cc",
    HISTORY / "results" / "ns3",
    HISTORY / "results" / "cross_platform",
    HISTORY / "docs" / "PreDay18_最终止损报告.md",
    HISTORY / "results" / "cross_platform" / "stop_loss_decision.json",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_manifest() -> dict:
    files: dict[str, str] = {}
    for target in TARGETS:
        candidates = sorted(p for p in target.rglob("*") if p.is_file()) if target.is_dir() else [target]
        for path in candidates:
            files[path.relative_to(REPO_ROOT).as_posix()] = sha256(path)
    return {
        "algorithm": "SHA256",
        "base_commit": "1292d3a0c21199e7baa9184179371f9bf6b69d00",
        "immutable_root": "daily/PreDay18_最小止损路线/",
        "file_count": len(files),
        "files": files,
    }


def write_or_verify(path: Path) -> dict:
    current = collect_manifest()
    if path.exists():
        expected = json.loads(path.read_text(encoding="utf-8"))
        if expected != current:
            raise AssertionError("Original PreDay18 evidence SHA256 manifest changed")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return current
