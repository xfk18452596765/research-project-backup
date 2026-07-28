"""Run Day16 checks with UTF-8-safe log and JSON handling.

Default behavior runs the Day16 tests, main validation, and Day03-Day16 full
regression.  ``--skip-regression`` is only for an isolated compatibility check;
it does not complete the project's daily closure.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

CURRENT_DIR = Path(__file__).resolve().parent
DAY_DIR = CURRENT_DIR.parent
DAILY_DIR = DAY_DIR.parent
REPO_ROOT = DAILY_DIR.parent
LOG_DIR = DAY_DIR / "logs"
RESULT_DIR = DAY_DIR / "results"


def run_python(script: Path) -> str:
    if not script.exists():
        raise FileNotFoundError(f"Missing Python entrypoint: {script}")
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
        output += ("\n" if output else "") + completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(
            f"{script.name} failed with exit code {completed.returncode}.\n{output}"
        )
    return output


def write_utf8(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def clean_python_cache() -> None:
    for cache_dir in DAILY_DIR.rglob("__pycache__"):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
    for bytecode in DAILY_DIR.rglob("*.pyc"):
        bytecode.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-regression",
        action="store_true",
        help="Run only isolated Day16 checks; does not complete the daily closure.",
    )
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    test_output = run_python(CURRENT_DIR / "test_rl_prmac_reward_update.py")
    write_utf8(LOG_DIR / "day16_reward_update_tests.log", test_output)
    write_utf8(DAY_DIR / "test_results.txt", test_output)
    if "All Day16 reward/update tests passed." not in test_output:
        raise RuntimeError("Day16 test success marker is missing.")

    validation_output = run_python(
        CURRENT_DIR / "main_day16_reward_update_validation.py"
    )
    payload = json.loads(validation_output)
    if payload.get("day") != "Day16":
        raise RuntimeError("Day16 main validation JSON has an invalid day marker.")
    normalized_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    write_utf8(LOG_DIR / "main_day16_reward_update_validation.log", normalized_json)
    write_utf8(RESULT_DIR / "day16_reward_update_validation.json", normalized_json)

    if not args.skip_regression:
        regression_output = run_python(CURRENT_DIR / "run_day03_day16_regression.py")
        write_utf8(LOG_DIR / "day03_day16_regression.log", regression_output)
        if "All Day03-Day16 regression tests passed." not in regression_output:
            raise RuntimeError("Day03-Day16 regression success marker is missing.")

    clean_python_cache()
    print("All Day16 reward/update tests passed.")
    print("Day16 main validation JSON is UTF-8 and parseable.")
    if args.skip_regression:
        print("Day03-Day16 regression was skipped; daily closure is NOT complete.")
    else:
        print("All Day03-Day16 regression tests passed.")
        print("Day16 validation closure completed.")


if __name__ == "__main__":
    main()
