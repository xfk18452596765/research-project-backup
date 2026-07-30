from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from common import REPO


class ScopeGuardTest(unittest.TestCase):
    def test_all_worktree_changes_are_in_new_stage(self) -> None:
        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=REPO,
            capture_output=True,
            check=True,
        )
        lines = completed.stdout.decode("utf-8", errors="replace").splitlines()
        outside = [
            line
            for line in lines
            if "daily/PreDay18_ns3" not in line.replace("\\", "/")
        ]
        self.assertEqual(outside, [])

    def test_source_has_no_rl_integration(self) -> None:
        stage = CODE.parent
        checked = [
            stage / "ns3" / "overlay" / "scratch" / "preday18-semantic-baseline.cc",
            stage / "code" / "run_semantic_checks.py",
            stage / "code" / "run_baseline_smoke.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in checked)
        self.assertNotIn("Q-learning", source)
        self.assertNotIn("RL-PRMAC performance", source)


if __name__ == "__main__":
    unittest.main()
