"""SQLite analytics and read-only API integration tests."""

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from fastapi.testclient import TestClient

from yottaflex_debt_collection.api import create_app
from yottaflex_debt_collection.database import connect_readonly, load_dataset
from yottaflex_debt_collection.generator import generate_dataset


ROOT = Path(__file__).resolve().parents[1]


class DatabaseAnalyticsTests(unittest.TestCase):
    def test_sql_views_match_independent_pandas_recomputation(self) -> None:
        with TemporaryDirectory() as output_dir:
            generate_dataset(
                300,
                20261022,
                output_dir,
                inject_anomalies=True,
                anomaly_rows_per_type=3,
                dataset_name="full",
            )
            root = Path(output_dir)
            data_dir = root / "data" / "full"
            ground_truth_dir = root / "ground_truth" / "full"
            db_path = data_dir / "analytics.sqlite"
            counts = load_dataset(data_dir, db_path, ground_truth_dir)
            self.assertEqual(counts["loan"], 300)
            connection = connect_readonly(db_path)
            try:
                self.assertEqual(
                    connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
                )
                actual_latest = {
                    row["loan_id"]: row["snapshot_id"]
                    for row in connection.execute(
                        "SELECT loan_id, snapshot_id FROM latest_snapshot"
                    )
                }
                actual_roll = {
                    (row["from_bucket"], row["to_bucket"]): row["loan_transitions"]
                    for row in connection.execute("SELECT * FROM roll_rates")
                }
                actual_promises = {
                    row["segment"]: (
                        row["promise_count"],
                        row["kept_count"],
                        row["kept_rate"],
                    )
                    for row in connection.execute("SELECT * FROM promise_kept_by_segment")
                }
                actual_cure = dict(
                    connection.execute("SELECT * FROM cure_rate").fetchone()
                )
                actual_violations = {
                    (row["rule_id"], row["decision_type"], row["outcome"]): row[
                        "decision_count"
                    ]
                    for row in connection.execute("SELECT * FROM violations_by_rule")
                }
                actual_queue = {
                    row["case_id"]: (
                        row["days_past_due"],
                        row["arrears_amount"],
                    )
                    for row in connection.execute("SELECT * FROM priority_queue")
                }
            finally:
                connection.close()

            snapshots = pd.read_csv(data_dir / "delinquency_snapshot.csv")
            reason_rank = {"as_of": 0, "case_open": 1, "month_end": 2}
            snapshots["reason_rank"] = snapshots["snapshot_reason"].map(reason_rank)
            expected_latest_frame = snapshots.sort_values(
                ["loan_id", "snapshot_date", "reason_rank", "snapshot_id"],
                ascending=[True, False, True, False],
            ).drop_duplicates("loan_id")
            expected_latest = dict(
                zip(expected_latest_frame["loan_id"], expected_latest_frame["snapshot_id"])
            )
            self.assertEqual(actual_latest, expected_latest)

            monthly = snapshots[snapshots["snapshot_reason"] == "month_end"].copy()

            def delinquency_bucket(days: int) -> str:
                if days == 0:
                    return "current"
                if days <= 30:
                    return "1_30"
                if days <= 60:
                    return "31_60"
                if days <= 90:
                    return "61_90"
                return "90_plus"

            monthly["bucket"] = monthly["days_past_due"].map(delinquency_bucket)
            monthly = monthly.sort_values(["loan_id", "snapshot_date"])
            monthly["from_bucket"] = monthly.groupby("loan_id")["bucket"].shift(1)
            expected_roll = (
                monthly.dropna(subset=["from_bucket"])
                .groupby(["from_bucket", "bucket"])
                .size()
                .to_dict()
            )
            self.assertEqual(
                actual_roll,
                {(str(key[0]), str(key[1])): int(value) for key, value in expected_roll.items()},
            )

            segments = pd.read_csv(ground_truth_dir / "latent_segments.csv")
            cases = pd.read_csv(data_dir / "collection_case.csv")
            loans = pd.read_csv(data_dir / "loan.csv")
            promises = pd.read_csv(data_dir / "promise_to_pay.csv")
            segment_cases = (
                segments.merge(loans[["loan_id"]], on="loan_id")
                .merge(cases[["loan_id", "case_id"]], on="loan_id")
                .merge(promises[["case_id", "promise_id", "status"]], on="case_id", how="left")
            )
            segment_summary = (
                segment_cases.groupby("segment")
                .agg(
                    promise_count=("promise_id", "count"),
                    kept_count=("status", lambda values: (values == "KEPT").sum()),
                )
            )
            expected_promises = {
                segment: (
                    int(row["promise_count"]),
                    int(row["kept_count"]),
                    (
                        float(row["kept_count"]) / float(row["promise_count"])
                        if row["promise_count"]
                        else 0.0
                    ),
                )
                for segment, row in segment_summary.iterrows()
            }
            for segment, (count, kept, rate) in expected_promises.items():
                self.assertEqual(
                    actual_promises[segment][:2],
                    (count, kept),
                )
                self.assertAlmostEqual(actual_promises[segment][2], rate)

            case_open = snapshots[snapshots["snapshot_reason"] == "case_open"].groupby(
                "loan_id"
            )["days_past_due"].max()
            latest = expected_latest_frame.set_index("loan_id")["days_past_due"]
            cure_rows = pd.concat(
                [case_open.rename("initial"), latest.rename("latest")],
                axis=1,
                join="inner",
            )
            cured_count = int(
                ((cure_rows["initial"] > 0) & (cure_rows["latest"] == 0)).sum()
            )
            self.assertEqual(actual_cure["delinquent_loans"], len(cure_rows))
            self.assertEqual(actual_cure["cured_loans"], cured_count)
            self.assertAlmostEqual(
                actual_cure["cure_rate"],
                cured_count / len(cure_rows) if len(cure_rows) else 0,
            )

            decisions = pd.read_csv(data_dir / "decision_log.csv")
            violations = decisions[
                decisions["outcome"].isin(["block", "review", "close"])
            ]
            expected_violations = (
                violations.groupby(["rule_id", "decision_type", "outcome"])
                .size()
                .to_dict()
            )
            self.assertEqual(
                actual_violations,
                {tuple(key): int(value) for key, value in expected_violations.items()},
            )

            open_cases = cases[cases["status"] == "open"]
            latest_by_loan = expected_latest_frame.set_index("loan_id")
            expected_queue = {
                row["case_id"]: (
                    int(latest_by_loan.loc[row["loan_id"], "days_past_due"]),
                    int(latest_by_loan.loc[row["loan_id"], "arrears_amount"]),
                )
                for _, row in open_cases.iterrows()
            }
            self.assertEqual(actual_queue, expected_queue)

    def test_loader_enforces_foreign_keys_and_protects_existing_database(self) -> None:
        with TemporaryDirectory() as output_dir:
            generate_dataset(40, 4, output_dir, dataset_name="full")
            data_dir = Path(output_dir) / "data" / "full"
            db_path = data_dir / "collection.sqlite"
            load_dataset(data_dir, db_path)
            with self.assertRaises(FileExistsError):
                load_dataset(data_dir, db_path)

            connection = sqlite3.connect(db_path)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO account
                            (account_id, customer_id, account_status, hardship_status, opened_at)
                        VALUES ('ACC-999999', 'CUS-999999', 'open', 'none', '2026-01-01')
                        """
                    )
            finally:
                connection.close()


class ApiTests(unittest.TestCase):
    def test_read_only_endpoints_cover_suppressed_and_blocked_contact_cases(self) -> None:
        with TemporaryDirectory() as output_dir:
            dataset = generate_dataset(
                500,
                20261022,
                output_dir,
                inject_anomalies=True,
                anomaly_rows_per_type=5,
                dataset_name="full",
            )
            root = Path(output_dir)
            data_dir = root / "data" / "full"
            labels_dir = root / "ground_truth" / "full"
            db_path = data_dir / "api.sqlite"
            load_dataset(data_dir, db_path, labels_dir)
            client = TestClient(
                create_app(
                    data_dir=data_dir,
                    db_path=db_path,
                    ground_truth_dir=labels_dir,
                    policy_path=ROOT / "config" / "policy.yaml",
                )
            )

            self.assertEqual(client.get("/health").json()["status"], "ok")
            queue = client.get("/queue", params={"limit": 10})
            self.assertEqual(queue.status_code, 200)
            scores = [
                row["priority_score"] for row in queue.json()["items"]
            ]
            self.assertEqual(scores, sorted(scores, reverse=True))
            case_id = str(queue.json()["items"][0]["case_id"])
            detail = client.get(f"/cases/{case_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["case_id"], case_id)
            self.assertTrue(
                client.get(f"/cases/{case_id}/timeline").json()["events"]
            )
            self.assertTrue(
                client.get("/decisions", params={"case_id": case_id}).json()["items"]
            )
            self.assertIn("roll_rates", client.get("/metrics").json())
            self.assertTrue(client.get("/exceptions").json()["items"])
            self.assertIn("rules", client.get("/admin/policy").json())
            self.assertTrue(client.get("/admin/validation").json()["valid"])
            self.assertEqual(
                client.get("/admin/manifest").json()["loans"],
                500,
            )
            self.assertEqual(client.get("/cases/not-a-case").status_code, 404)

            suppressed = next(
                row for row in dataset["collection_case"] if row["suppression_rule_id"]
            )
            self.assertIn(
                client.get(f"/cases/{suppressed['case_id']}").json()["status"],
                {"paused", "resolved"},
            )
            blocked_case_ids = {
                str(attempt["case_id"])
                for attempt in dataset["contact_attempt"]
                if attempt["outcome"] == "policy_blocked"
            }
            self.assertTrue(blocked_case_ids)
            blocked_case_id = next(iter(blocked_case_ids))
            blocked_timeline = client.get(
                f"/cases/{blocked_case_id}/timeline"
            ).json()["events"]
            self.assertTrue(
                any(
                    event["event_type"] == "contact_attempt"
                    and event["summary"] == "policy_blocked"
                    for event in blocked_timeline
                )
            )
            blocked_decisions = client.get(
                "/decisions", params={"case_id": blocked_case_id}
            ).json()["items"]
            self.assertTrue(blocked_decisions)
            self.assertIn(blocked_decisions[0]["outcome"], {"review", "close"})


if __name__ == "__main__":
    unittest.main()
