from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable

STAGE = Path(__file__).resolve().parents[1]
REPO = STAGE.parents[1]
NS3_WORKTREE = "/home/xfk/workspace/ns-3.43-fixed-prmac-baseline"
NS3_PROGRAM = "scratch/preday18-semantic-baseline"


def wsl_path(path: Path) -> str:
    path = path.resolve()
    drive = path.drive.rstrip(":").lower()
    suffix = path.as_posix().split(":", 1)[1]
    return f"/mnt/{drive}{suffix}"


def ensure_result_dirs() -> None:
    for relative in (
        "results/audit",
        "results/topology",
        "results/semantic",
        "results/traces",
        "results/decision",
        "results/smoke",
        "logs",
    ):
        (STAGE / relative).mkdir(parents=True, exist_ok=True)


def run_wsl(command: str, log_name: str, timeout: int = 1800) -> subprocess.CompletedProcess[bytes]:
    ensure_result_dirs()
    completed = subprocess.run(
        ["wsl.exe", "-e", "bash", "-lc", command],
        cwd=REPO,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    (STAGE / "logs" / f"{log_name}.stdout.log").write_text(stdout, encoding="utf-8")
    (STAGE / "logs" / f"{log_name}.stderr.log").write_text(stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(
            f"WSL command failed ({completed.returncode}); see logs/{log_name}.*.log"
        )
    return completed


def case_id(
    protocol: str,
    hops: int,
    packets: int,
    traffic: str,
    load: str,
    seed: int,
    scenario: str = "chain",
) -> str:
    return (
        f"{scenario}-{protocol}-{hops}hop-{packets}pkt-"
        f"{load}-{traffic}-seed{seed}"
    )


def run_case(
    *,
    protocol: str,
    hops: int,
    packets: int,
    traffic: str = "periodic",
    load: str = "low",
    seed: int = 7,
    scenario: str = "chain",
    flows: int = 1,
) -> dict[str, Any]:
    ensure_result_dirs()
    identity = case_id(protocol, hops, packets, traffic, load, seed, scenario)
    output = STAGE / "results" / "semantic" / f"{identity}.json"
    trace = STAGE / "results" / "traces" / f"{identity}.jsonl"
    command = " ".join(
        (
            f"cd {NS3_WORKTREE}",
            "&&",
            f"./ns3 run '{NS3_PROGRAM}",
            f"--protocol={protocol}",
            f"--scenario={scenario}",
            f"--hops={hops}",
            f"--packets={packets}",
            f"--flows={flows}",
            f"--traffic={traffic}",
            f"--load={load}",
            f"--seed={seed}",
            f"--output={wsl_path(output)}",
            f"--trace={wsl_path(trace)}'",
        )
    )
    run_wsl(command, f"case-{identity}")
    return json.loads(output.read_text(encoding="utf-8"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_trace(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def evidence_manifest(directory: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        entries.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    canonical = "\n".join(
        f"{entry['sha256']}  {entry['path']}" for entry in entries
    ).encode("utf-8")
    return {
        "directory": directory.relative_to(REPO).as_posix(),
        "file_count": len(entries),
        "manifest_sha256": hashlib.sha256(canonical).hexdigest(),
        "files": entries,
    }


def terminal_accounting(result: dict[str, Any]) -> tuple[bool, str]:
    counts = result["terminal_counts"]
    total = sum(counts.values())
    ok = (
        total == result["created"]
        and result["unknown_loss"] == 0
        and result["active_reservations_after_run"] == 0
    )
    return ok, f"created={result['created']} terminal_sum={total}"


def semantic_result_files() -> Iterable[Path]:
    paths = []
    for path in sorted((STAGE / "results" / "semantic").glob("*.json")):
        try:
            payload = load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict) and "terminal_counts" in payload:
            paths.append(path)
    return paths
