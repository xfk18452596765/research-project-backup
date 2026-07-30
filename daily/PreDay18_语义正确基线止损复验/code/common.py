from __future__ import annotations

import hashlib
import json
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
REPO = STAGE.parents[1]
HISTORICAL = [
    REPO / "daily" / "PreDay18_最小止损路线",
    REPO / "daily" / "PreDay18_Fixed-PRMAC机制诊断",
    REPO / "daily" / "PreDay18_ns3语义正确基线重建",
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_manifest(root: Path) -> dict:
    entries = []
    digest = hashlib.sha256()
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        file_sha = sha256_file(path)
        size = path.stat().st_size
        entries.append({"path": relative, "sha256": file_sha, "size": size})
        digest.update(f"{relative}\0{size}\0{file_sha}\n".encode())
    return {"directory": root.relative_to(REPO).as_posix(), "file_count": len(entries), "sha256": digest.hexdigest(), "files": entries}
