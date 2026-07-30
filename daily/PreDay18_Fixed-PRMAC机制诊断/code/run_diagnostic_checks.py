from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
LOG = ROOT / "logs" / "diagnostic_checks.log"


def run(command: list[str], cwd: Path = REPO) -> str:
    env = os.environ.copy()
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    process = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write("$ " + " ".join(command) + "\n" + process.stdout + "\n")
    print(process.stdout.encode("gbk", errors="replace").decode("gbk"), end="")
    process.check_returncode()
    return process.stdout


def main() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("", encoding="utf-8")
    wsl_script = "/mnt/c/research-project-backup/daily/PreDay18_Fixed-PRMAC机制诊断/ns3/scripts/run_diagnostic_matrix.sh"
    outputs = list((ROOT / "results" / "diagnostic_runs").glob("*.json"))
    traces = list((ROOT / "results" / "traces").glob("*.jsonl"))
    if len(outputs) == 188 and len(traces) == 188:
        message = "Reusing complete immutable diagnostic matrix: 188 summaries and 188 traces.\n"
        LOG.write_text(message, encoding="utf-8")
        print(message, end="")
    else:
        run(["wsl.exe", "-e", "bash", wsl_script])
    run([sys.executable, str(ROOT / "code" / "analysis" / "analyze_results.py")])
    run([sys.executable, str(ROOT / "code" / "tests" / "test_diagnostic.py")])
    print("Diagnostic matrix and focused tests passed.")


if __name__ == "__main__":
    main()
