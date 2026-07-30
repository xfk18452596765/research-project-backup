from __future__ import annotations

import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from analysis.validate_k2_lifecycle import validate, validate_retry
from common import STAGE, load_json, read_trace


class FixedK2LifecycleTest(unittest.TestCase):
    def test_single_packet_segments(self) -> None:
        for hops in (2, 4, 6):
            stem = f"chain-fixed-{hops}hop-1pkt-low-periodic-seed7"
            result = load_json(STAGE / "results" / "semantic" / f"{stem}.json")
            self.assertEqual(result["delivered"], 1)
            self.assertEqual(result["packets_detail"][0]["segments_completed"], hops // 2)
            passed, issues = validate(
                read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl"), hops
            )
            self.assertTrue(passed, issues)

    def test_pr_nack_triggers_beb_and_fresh_attempt(self) -> None:
        stem = "reservation-conflict-fixed-2hop-1pkt-low-periodic-seed7"
        passed, issues = validate_retry(
            read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl")
        )
        self.assertTrue(passed, issues)
        result = load_json(STAGE / "results" / "semantic" / f"{stem}.json")
        self.assertEqual(result["delivered"], 1)


if __name__ == "__main__":
    unittest.main()
