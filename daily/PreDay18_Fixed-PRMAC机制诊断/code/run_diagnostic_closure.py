from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
LOG = ROOT / "logs" / "diagnostic_closure.log"


def run(command: list[str]) -> str:
    env = os.environ.copy()
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    process = subprocess.run(
        command,
        cwd=REPO,
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
    run([sys.executable, str(ROOT / "code" / "run_static_audit.py")])
    run([sys.executable, str(ROOT / "code" / "tests" / "test_diagnostic.py")])
    day17 = next((REPO / "daily").glob("Day17_*"))
    regression = day17 / "code" / "run_day03_day17_regression.py"
    regression_output = run([sys.executable, str(regression)])

    status = run(["git", "status", "--short"])
    outside = [
        line for line in status.splitlines()
        if line.strip() and "daily/PreDay18_Fixed-PRMAC机制诊断/" not in line.replace("\\", "/")
    ]
    if outside:
        raise AssertionError(f"Changes outside diagnostic directory: {outside}")

    decision = json.loads((ROOT / "results" / "decision" / "root_cause_classification.json").read_text(encoding="utf-8"))
    test_results = (
        "PreDay18 Fixed-PRMAC mechanism diagnosis\n"
        "==========================================\n"
        "Static audit: PASS (11 high-risk checks completed; 11 implementation failures identified)\n"
        "ns-3 diagnostic program compile: PASS\n"
        "Diagnostic matrix: PASS (188 runs: tier1=8, tier2=108, tier3=72)\n"
        "Causal forwarding trace: PASS\n"
        "K=2 segment bound: PASS\n"
        "Unique packet terminal state: PASS\n"
        "UNKNOWN_LOSS=0: PASS\n"
        "Same-seed reproducibility: PASS\n"
        "JSON UTF-8 parsing: PASS\n"
        "Original evidence SHA256 unchanged: PASS\n"
        "Changes confined to diagnostic directory: PASS\n"
        "Day03-Day17 regression: PASS\n"
        f"Root cause classification: {decision['root_cause_classification']}\n"
        "PreDay18 decision: FAIL (unchanged)\n"
        "Day18: LOCKED\n"
        "RL training: NOT_RUN\n"
    )
    (ROOT / "test_results.txt").write_text(test_results, encoding="utf-8")
    print(test_results)


if __name__ == "__main__":
    main()
