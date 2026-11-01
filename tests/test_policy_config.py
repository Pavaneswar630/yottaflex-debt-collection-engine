"""Tests for policy configuration shape and internal consistency."""

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
        cls.dictionary = load_yaml(ROOT / "schema" / "data_dictionary.yaml")
        cls.tables = {
            table["name"]: table for table in cls.dictionary["tables"]
        }

    def test_contact_windows_and_attempt_limit_are_configured(self) -> None:
        contact = self.policy["contact"]
        self.assertEqual(
            contact["timezone_source"], "contact_preference.timezone"
        )
        weekdays = contact["windows"]["weekdays"]
        self.assertEqual(weekdays["days"], [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
        ])
        self.assertLess(weekdays["start_local"], weekdays["end_local"])
        self.assertFalse(contact["windows"]["weekends"]["allowed"])
        self.assertEqual(contact["max_attempts_per_week"]["count"], 3)
        self.assertEqual(contact["max_attempts_per_week"]["period_days"], 7)
        self.assertTrue(contact["max_attempts_per_week"]["rolling_period"])
        self.assertIn(
            "policy_blocked",
            contact["max_attempts_per_week"]["excluded_outcomes"],
        )

    def test_allocation_and_scoring_rules_are_complete(self) -> None:
        allocation = self.policy["payment_allocation"]
        self.assertEqual(allocation["rule"], "oldest_due_first")
        self.assertTrue(allocation["allow_partial_allocation"])
        self.assertEqual(allocation["eligible_payment_statuses"], ["posted"])
        self.assertEqual(
            set(allocation["tie_breakers"]),
            {"due_date", "loan_id", "sequence_number"},
        )

        scoring = self.policy["scoring"]
        self.assertEqual(
            set(scoring["weights"]),
            {"arrears_amount", "dpd_bucket", "risk_score"},
        )
        self.assertAlmostEqual(sum(scoring["weights"].values()), 1.0)
        self.assertEqual(scoring["scale"], {"minimum": 0, "maximum": 100})

    def test_dpd_buckets_are_contiguous_and_cover_unbounded_delinquency(self) -> None:
        buckets = self.policy["dpd_buckets"]
        self.assertTrue(buckets)
        self.assertEqual(buckets[0]["min_days"], 0)
        for index, bucket in enumerate(buckets):
            self.assertGreaterEqual(bucket["score"], 0)
            self.assertLessEqual(bucket["score"], 100)
            if index < len(buckets) - 1:
                self.assertEqual(
                    buckets[index + 1]["min_days"],
                    bucket["max_days"] + 1,
                )
                self.assertIsNotNone(bucket["max_days"])
        self.assertEqual(buckets[-1]["max_days"], None)

    def test_hold_statuses_match_the_data_dictionary_enums(self) -> None:
        dispute_statuses = self.tables["delinquency_snapshot"]["fields"][
            "dispute_status"
        ]["enum"]
        hardship_statuses = self.tables["account"]["fields"][
            "hardship_status"
        ]["enum"]

        self.assertTrue(
            set(self.policy["holds"]["dispute"]["statuses"])
            <= set(dispute_statuses)
        )
        self.assertTrue(
            set(self.policy["holds"]["dispute"]["release_statuses"])
            <= set(dispute_statuses)
        )
        self.assertTrue(
            set(self.policy["holds"]["hardship"]["statuses"])
            <= set(hardship_statuses)
        )
        self.assertTrue(
            set(self.policy["holds"]["hardship"]["release_statuses"])
            <= set(hardship_statuses)
        )
        for hold in self.policy["holds"].values():
            self.assertTrue(hold["pause_outbound_contact"])
            self.assertTrue(hold["pause_automated_escalation"])


if __name__ == "__main__":
    unittest.main()
