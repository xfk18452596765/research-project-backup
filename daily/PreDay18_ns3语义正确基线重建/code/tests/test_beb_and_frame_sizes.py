from __future__ import annotations

import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from analysis.validate_beb_and_frame_sizes import expected_cw, validate_source
from common import STAGE


class BebAndFrameSizeTest(unittest.TestCase):
    def test_beb_formula(self) -> None:
        self.assertEqual(
            [expected_cw(n) for n in range(1, 9)],
            [31, 63, 127, 255, 511, 1023, 1023, 1023],
        )

    def test_frame_construction(self) -> None:
        source = (
            STAGE
            / "ns3"
            / "overlay"
            / "scratch"
            / "preday18-semantic-baseline.cc"
        ).read_text(encoding="utf-8")
        passed, issues = validate_source(source)
        self.assertTrue(passed, issues)


if __name__ == "__main__":
    unittest.main()
