"""Run Day03-Day10 regression tests in order."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
DAILY_DIR = CURRENT_DIR.parents[1]

TEST_FILES = [
    DAILY_DIR / "Day03_仿真架构与事件设计" / "code" / "test_core_components.py",
    DAILY_DIR / "Day04_DCF基础框架" / "code" / "test_dcf_single_hop.py",
    DAILY_DIR / "Day05_DCF信道忙与退避冻结" / "code" / "test_dcf_busy_freeze.py",
    DAILY_DIR / "Day06_DCF碰撞与重传" / "code" / "test_dcf_collision_retry.py",
    DAILY_DIR / "Day07_DCF指标采集" / "code" / "test_dcf_multihop_metrics.py",
    DAILY_DIR / "Day08_DCF验证与调试" / "code" / "test_dcf_validation.py",
    DAILY_DIR / "Day09_Fixed-PRMAC报文与预约" / "code" / "test_fixed_prmac_reservation.py",
    CURRENT_DIR / "test_fixed_prmac_conflict.py",
]


def main() -> None:
    for test_file in TEST_FILES:
        if not test_file.exists():
            raise FileNotFoundError(f"Missing regression test: {test_file}")
        print(f"\n=== Running {test_file.relative_to(DAILY_DIR)} ===", flush=True)
        subprocess.run([sys.executable, str(test_file)], check=True)

    print("\nAll Day03-Day10 regression tests passed.")


if __name__ == "__main__":
    main()
