from __future__ import annotations

import sys
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE))
from common import REPO, STAGE, evidence_manifest, load_json


class EvidenceImmutableTest(unittest.TestCase):
    def test_current_evidence_matches_start_manifest(self) -> None:
        start = load_json(
            STAGE / "results" / "audit" / "historical_evidence_start.json"
        )
        directories = [
            REPO / "daily" / "PreDay18_最小止损路线",
            REPO / "daily" / "PreDay18_Fixed-PRMAC机制诊断",
        ]
        current = [evidence_manifest(path) for path in directories]
        self.assertEqual(
            [item["manifest_sha256"] for item in start["directories"]],
            [item["manifest_sha256"] for item in current],
        )


if __name__ == "__main__":
    unittest.main()
