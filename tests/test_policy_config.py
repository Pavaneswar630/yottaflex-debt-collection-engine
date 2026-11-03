"""Tests for policy rule IDs, scoring, and reconciliation settings."""

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as source_file:
        return yaml.safe_load(source_file)


class PolicyConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_yaml(ROOT / "config" / "policy.yaml")

    def test_required_rules_are_id_addressable(self) -> None:
        rules = self.policy["rules"]
        required_rules = {
            "R-CONTACT-01",
            "R-CONTACT-02",
            "R-DISPUTE-01",
            "R-HARDSHIP-01",
            "R-CEASE-01",
            "R-PAIDOFF-01",
            "R-SCORE-01",
            "R-CASE-01",
            "R-RECON-01",
        }
        self.assertTrue(required_rules <= rules.keys())
        for rule_id, rule in rules.items():
            with self.subTest(rule_id=rule_id):
                self.assertRegex(rule_id, r"^R-[A-Z]+-\d{2}$")
                self.assertTrue(rule["desc"].strip())

    def test_suppression_precedence_is_explicit_and_ordered(self) -> None:
        self.assertEqual(
            self.policy["suppression"]["first_match_order"],
            [
                "R-PAIDOFF-01",
                "R-DISPUTE-01",
                "R-HARDSHIP-01",
                "R-CEASE-01",
            ],
        )
        self.assertEqual(
            self.policy["suppression"]["disposition"],
            {
                "R-PAIDOFF-01": "resolved",
                "R-DISPUTE-01": "paused",
                "R-HARDSHIP-01": "paused",
                "R-CEASE-01": "paused",
            },
        )

    def test_contact_and_exception_rules_have_operational_parameters(self) -> None:
        rules = self.policy["rules"]
        self.assertEqual(rules["R-CONTACT-01"]["start_local"], "08:00")
        self.assertEqual(rules["R-CONTACT-01"]["end_local"], "19:00")
        self.assertEqual(rules["R-CONTACT-01"]["timezone_source"], "contact_preference.timezone")
        self.assertEqual(rules["R-CONTACT-02"]["max_attempts"], 3)
        self.assertEqual(rules["R-CONTACT-02"]["period_days"], 7)
        self.assertEqual(rules["R-CONTACT-02"]["scope"], "account")
        self.assertTrue(rules["R-DISPUTE-01"]["suppress_dunning"])
        self.assertTrue(rules["R-DISPUTE-01"]["route_to_review"])
        self.assertTrue(rules["R-HARDSHIP-01"]["pause_outbound_contact"])
        self.assertTrue(rules["R-CEASE-01"]["block_outbound_contact"])
        self.assertTrue(rules["R-PAIDOFF-01"]["exclude_paid_off_loans"])

    def test_scoring_weights_and_dpd_buckets_are_valid(self) -> None:
        scoring = self.policy["scoring"]
        weights = [scoring["w_balance"], scoring["w_age"], scoring["w_risk"]]
        self.assertAlmostEqual(sum(weights), 1.0)
        self.assertEqual(scoring["scale"], {"minimum": 0, "maximum": 100})
        buckets = scoring["dpd_buckets"]
        self.assertTrue(buckets)
        self.assertEqual(buckets[0]["min_days"], 0)
        for index, bucket in enumerate(buckets):
            self.assertGreaterEqual(bucket["score"], 0)
            self.assertLessEqual(bucket["score"], 100)
            if index < len(buckets) - 1:
                self.assertEqual(buckets[index + 1]["min_days"], bucket["max_days"] + 1)
                self.assertIsNotNone(bucket["max_days"])
        self.assertIsNone(buckets[-1]["max_days"])
        self.assertEqual(self.policy["rules"]["R-CASE-01"]["dpd_threshold"], 1)
        self.assertEqual(scoring["tiers"], {"p1_min_score": 70, "p2_min_score": 40})
        self.assertEqual(
            scoring["balance_normalization"],
            "min(arrears_amount / loan.principal_amount, 1)",
        )
        self.assertIn("100 *", scoring["formula"])
        self.assertIn("normalized DPD bucket score", scoring["formula"])

    def test_reconciliation_tolerance_and_grace_period_are_explicit(self) -> None:
        self.assertEqual(self.policy["reconcile"]["tolerance_pct"], 5)
        self.assertEqual(self.policy["reconcile"]["grace_days"], 2)


if __name__ == "__main__":
    unittest.main()
