from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

STAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(STAGE / "code"))

from common import load_json, sha256_file
from run_retest_closure import ci95


class RetestEvidenceTest(unittest.TestCase):
    def test_policy_is_frozen(self):
        recorded = load_json(STAGE / "results" / "audit" / "stop_loss_policy_sha256.json")
        self.assertEqual(recorded["sha256"], sha256_file(STAGE / "configs" / "stop_loss_policy.json"))

    def test_matrix_counts(self):
        expected = {"precheck": 36, "broad_core": 360, "confirmatory": 320, "sensitivity": 200}
        for section, count in expected.items():
            files = list((STAGE / "results" / "ns3" / section / "raw").glob("*.json"))
            self.assertEqual(len(files), count, section)

    def test_result_schema_and_finiteness(self):
        required = {"platform", "protocol", "scenario_id", "seed", "created_packets",
                    "delivered_packets", "delivery_ratio", "average_e2e_delay",
                    "p95_e2e_delay", "throughput_bps", "unknown_loss_count",
                    "active_reservations_after_run", "source_sha", "patch_sha",
                    "config_sha", "traffic_schedule_sha", "topology_sha"}
        for section in ("precheck", "broad_core", "confirmatory", "sensitivity"):
            for path in (STAGE / "results" / "ns3" / section / "raw").glob("*.json"):
                row = load_json(path)
                self.assertFalse(required - set(row), path.name)
                for value in row.values():
                    if isinstance(value, float):
                        self.assertTrue(math.isfinite(value), path.name)

    def test_pairing_and_integrity(self):
        for section in ("precheck", "broad_core", "confirmatory", "sensitivity"):
            summary = load_json(STAGE / "results" / "ns3" / section / "aggregate" / "execution_summary.json")
            self.assertFalse(summary["failures"])
            self.assertFalse(summary["integrity_issues"])

    def test_bootstrap_reproducible(self):
        values = [-2.0, -1.0, 0.0, 1.0]
        self.assertEqual(ci95(values, 42), ci95(values, 42))

    def test_historical_evidence_immutable(self):
        comparison = load_json(STAGE / "results" / "audit" / "historical_evidence_comparison.json")
        self.assertTrue(comparison["passed"])

    def test_no_rl_and_day18_locked(self):
        decision = load_json(STAGE / "results" / "decision" / "stop_loss_decision.json")
        self.assertFalse(decision["RL_started"])
        self.assertEqual(decision["Day18_status"], "LOCKED")

    def test_decision_is_not_false_pass(self):
        decision = load_json(STAGE / "results" / "decision" / "stop_loss_decision.json")
        self.assertEqual(decision["decision"], "FAIL")
        self.assertFalse(decision["thresholds"]["core_delay"])
        self.assertFalse(decision["thresholds"]["delivery"])


if __name__ == "__main__":
    unittest.main()
