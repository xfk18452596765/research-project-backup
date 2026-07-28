"""Run the complete UTF-8-safe Day17 validation closure."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

CURRENT_DIR = Path(__file__).resolve().parent
DAY17_DIR = CURRENT_DIR.parent
DAILY_DIR = DAY17_DIR.parent
REPO_ROOT = DAILY_DIR.parent
LOG_DIR = DAY17_DIR / "logs"
RESULT_DIR = DAY17_DIR / "results"

TEST_SCRIPT = CURRENT_DIR / "test_rl_prmac_protocol_controller.py"
MAIN_SCRIPT = CURRENT_DIR / "main_day17_protocol_integration_validation.py"
REGRESSION_SCRIPT = CURRENT_DIR / "run_day03_day17_regression.py"


def run_script(script: Path) -> str:
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=child_env,
        check=False,
    )
    output = completed.stdout
    if completed.stderr:
        output += completed.stderr
    if completed.returncode != 0:
        print(output, end="")
        raise RuntimeError(
            f"{script.name} failed with exit code {completed.returncode}."
        )
    return output


def write_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def remove_python_cache(root: Path) -> None:
    for cache in root.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache)
    for pyc in root.rglob("*.pyc"):
        if pyc.is_file():
            pyc.unlink()


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    test_output = run_script(TEST_SCRIPT)
    write_utf8(LOG_DIR / "day17_protocol_controller_tests.log", test_output)
    print("All Day17 protocol-controller tests passed.")

    main_output = run_script(MAIN_SCRIPT)
    payload = json.loads(main_output)
    if payload.get("day") != "Day17":
        raise ValueError("Day17 main validation JSON has an unexpected day field.")
    if not payload.get("session", {}).get("delivered"):
        raise ValueError("Day17 main validation session was not delivered.")
    if payload.get("learning", {}).get("pending_nodes_after_flush") != []:
        raise ValueError("Day17 main validation left pending local experiences.")
    write_utf8(LOG_DIR / "main_day17_protocol_integration_validation.log", main_output)
    write_utf8(
        RESULT_DIR / "day17_protocol_integration_validation.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    # Verify the exact bytes written by this machine are UTF-8 and parseable.
    saved = (
        RESULT_DIR / "day17_protocol_integration_validation.json"
    ).read_bytes().decode("utf-8")
    json.loads(saved)
    print("Day17 main validation JSON is UTF-8 and parseable.")

    regression_output = run_script(REGRESSION_SCRIPT)
    write_utf8(LOG_DIR / "day03_day17_regression.log", regression_output)
    if "All Day03-Day17 regression tests passed." not in regression_output:
        raise RuntimeError("Day17 regression success marker is missing.")
    print("All Day03-Day17 regression tests passed.")

    summary = "\n".join(
        [
            "Day17 validation closure",
            "All Day17 protocol-controller tests passed.",
            "Day17 main validation JSON is UTF-8 and parseable.",
            "All Day03-Day17 regression tests passed.",
            "Day17 validation closure completed.",
            "",
        ]
    )
    write_utf8(DAY17_DIR / "test_results.txt", summary)
    remove_python_cache(REPO_ROOT)
    print("Day17 validation closure completed.")


if __name__ == "__main__":
    main()
