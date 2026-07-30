from __future__ import annotations

import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from analysis.validate_topology import validate_calibration
from common import STAGE, read_trace


class TopologySemanticsTest(unittest.TestCase):
    def test_calibrated_chain_is_not_fully_connected(self) -> None:
        trace = read_trace(
            STAGE
            / "results"
            / "traces"
            / "calibration-dcf-6hop-1pkt-low-periodic-seed7.jsonl"
        )
        passed, issues = validate_calibration(
            trace, 7, STAGE / "results" / "topology"
        )
        self.assertTrue(passed, issues)


if __name__ == "__main__":
    unittest.main()
