from __future__ import annotations

import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from analysis.validate_causal_forwarding import validate
from common import STAGE, load_json, read_trace


class DcfCausalityTest(unittest.TestCase):
    def test_single_packet_receive_before_forward(self) -> None:
        for hops in (1, 2, 4, 6):
            stem = f"chain-dcf-{hops}hop-1pkt-low-periodic-seed7"
            result = load_json(STAGE / "results" / "semantic" / f"{stem}.json")
            self.assertEqual(result["delivered"], 1)
            passed, issues = validate(
                read_trace(STAGE / "results" / "traces" / f"{stem}.jsonl"), hops
            )
            self.assertTrue(passed, issues)


if __name__ == "__main__":
    unittest.main()
