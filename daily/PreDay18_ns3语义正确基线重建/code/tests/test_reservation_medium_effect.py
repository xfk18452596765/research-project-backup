from __future__ import annotations

import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from analysis.validate_medium_effect import validate
from common import STAGE, load_json, read_trace


class ReservationMediumEffectTest(unittest.TestCase):
    def test_txop_reserved_and_local_block_paths_are_observed(self) -> None:
        stem = "chain-fixed-6hop-1pkt-low-periodic-seed7"
        passed, issues = validate(
            load_json(STAGE / "results" / "semantic" / f"{stem}.json"),
            read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl"),
        )
        self.assertTrue(passed, issues)


if __name__ == "__main__":
    unittest.main()
