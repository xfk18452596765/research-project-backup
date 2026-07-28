"""Run Day03-Day17 regression tests in repository order."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

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
    DAILY_DIR / "Day10_Fixed-PRMAC冲突模型" / "code" / "test_fixed_prmac_conflict.py",
    DAILY_DIR / "Day11_Fixed-PRMAC连续转发" / "code" / "test_fixed_prmac_forwarding.py",
    DAILY_DIR / "Day12_Fixed-PRMAC失败与重传" / "code" / "test_fixed_prmac_retry.py",
    DAILY_DIR / "Day13_Fixed-PRMAC验证" / "code" / "test_fixed_prmac_validation.py",
    DAILY_DIR / "Day14_Q-learning状态设计" / "code" / "test_rl_prmac_state.py",
    DAILY_DIR / "Day15_Q-learning动作与策略" / "code" / "test_rl_prmac_action_policy.py",
    DAILY_DIR / "Day16_奖励函数与更新机制" / "code" / "test_rl_prmac_reward_update.py",
    CURRENT_DIR / "test_rl_prmac_protocol_controller.py",
]


def main() -> None:
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    for test in TEST_FILES:
        if not test.exists():
            raise FileNotFoundError(f"Missing regression test: {test}")
        print(f"\n=== Running {test.relative_to(DAILY_DIR)} ===", flush=True)
        subprocess.run(
            [sys.executable, str(test)],
            check=True,
            env=child_env,
        )
    print("\nAll Day03-Day17 regression tests passed.")


if __name__ == "__main__":
    main()
