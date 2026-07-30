from __future__ import annotations

import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from analysis.validate_loss_accounting import validate
from common import load_json, semantic_result_files


class LossAccountingTest(unittest.TestCase):
    def test_every_result_has_exact_terminal_accounting(self) -> None:
        files = list(semantic_result_files())
        self.assertGreaterEqual(len(files), 59)
        for path in files:
            passed, issues = validate(load_json(path))
            self.assertTrue(passed, f"{path.name}: {issues}")


if __name__ == "__main__":
    unittest.main()
