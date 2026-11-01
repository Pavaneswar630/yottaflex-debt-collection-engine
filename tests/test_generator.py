"""Tests for deterministic records, schedules, labels, and payment allocation."""

import csv
import hashlib
import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from yottaflex_debt_collection.generator import (
    CSV_COLUMNS,
    SEGMENT_PROBABILITIES,
    generate_dataset,
)
from yottaflex_debt_collection.schema_loader import load_dictionary
from yottaflex_debt_collection.settings import AS_OF_DATE


class GeneratorTests(unittest.TestCase):
    def test_export_columns_match_the_data_dictionary(self) -> None:
        schema_columns = {
            table.name: tuple(table.fields) for table in load_dictionary().tables
        }
        for table, columns in CSV_COLUMNS.items():
            with self.subTest(table=table):
                self.assertEqual(schema_columns[table], columns)

    def test_seed_repeats_records_and_export_checksums(self) -> None:
        with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
            first = generate_dataset(120, 71, first_dir)
            second = generate_dataset(120, 71, second_dir)
            self.assertEqual(first, second)

            first_files = sorted(Path(first_dir).rglob("*.csv"))
            second_files = sorted(Path(second_dir).rglob("*.csv"))
            self.assertEqual(
                [path.relative_to(first_dir) for path in first_files],
                [path.relative_to(second_dir) for path in second_files],
            )
            self.assertEqual(
                [
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in first_files
                ],
                [
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in second_files
                ],
            )

    def test_master_data_schedules_and_ground_truth_are_consistent(self) -> None:
        dataset = generate_dataset(2_000, 20261022)
        self.assertEqual(len(dataset["loan"]), 2_000)
        self.assertEqual(len(dataset["installment"]), 6_000)
        self.assertEqual(len(dataset["customer"]), 1_000)
        self.assertEqual(len(dataset["account"]), 2_000)
        self.assertEqual(len(dataset["contact_preference"]), 2_000)
        self.assertEqual(len(dataset["latent_segments"]), 2_000)
        accounts_per_customer = Counter(
            row["customer_id"] for row in dataset["account"]
        )
        self.assertTrue(all(count == 2 for count in accounts_per_customer.values()))
        self.assertTrue(
            all(
                row["risk_band"] in {"low", "medium", "high", "critical"}
                and row["timezone"]
                for row in dataset["customer"]
            )
        )

        segment_counts = Counter(row["segment"] for row in dataset["latent_segments"])
        for segment, weight in SEGMENT_PROBABILITIES.items():
            with self.subTest(segment=segment):
                self.assertAlmostEqual(
                    segment_counts[segment] / 2_000, weight, delta=0.025
                )

        loans_by_id = {row["loan_id"]: row for row in dataset["loan"]}
        installments_by_loan: dict[str, list[dict[str, str | int | bool | None]]] = {}
        for row in dataset["installment"]:
            installments_by_loan.setdefault(str(row["loan_id"]), []).append(row)
        for loan_id, installments in installments_by_loan.items():
            installments.sort(key=lambda row: int(row["sequence_number"]))
            self.assertEqual(len(installments), 3)
            self.assertEqual(
                sum(int(row["principal_due"]) for row in installments),
                int(loans_by_id[loan_id]["principal_amount"]),
            )
            principal = int(loans_by_id[loan_id]["principal_amount"])
            regular, remainder = divmod(principal, 3)
            self.assertEqual(
                [int(row["principal_due"]) for row in installments],
                [regular, regular, regular + remainder],
            )
            self.assertTrue(
                all(
                    installments[index]["due_date"] < installments[index + 1]["due_date"]
                    for index in range(2)
                )
            )
            self.assertLessEqual(
                max(str(row["due_date"]) for row in installments),
                AS_OF_DATE.isoformat(),
            )

        self.assertFalse(any("segment" in row for table in dataset.values() for row in table if table is not dataset["latent_segments"]))

    def test_contact_restrictions_and_optional_records_have_valid_parents(self) -> None:
        dataset = generate_dataset(500, 101)
        account_ids = {row["account_id"] for row in dataset["account"]}
        loan_ids = {row["loan_id"] for row in dataset["loan"]}
        accounts = {row["account_id"]: row for row in dataset["account"]}
        self.assertTrue(
            any(row["do_not_contact"] for row in dataset["contact_preference"])
        )
        self.assertTrue(dataset["dispute"])
        self.assertTrue(dataset["hardship_request"])
        for preference in dataset["contact_preference"]:
            self.assertIn(preference["account_id"], account_ids)
            self.assertGreaterEqual(
                str(preference["effective_from"]),
                str(accounts[preference["account_id"]]["opened_at"])[:10],
            )
            self.assertLessEqual("08:00:00", str(preference["allowed_start_time"]))
            self.assertLess(
                str(preference["allowed_start_time"]),
                str(preference["allowed_end_time"]),
            )
            self.assertLessEqual(str(preference["allowed_end_time"]), "19:00:00")
            self.assertIsInstance(preference["do_not_contact"], bool)
        for table in ("dispute", "hardship_request"):
            for record in dataset[table]:
                self.assertIn(record["account_id"], account_ids)
                self.assertIn(record["loan_id"], loan_ids)
                start_field = "filed_at" if table == "dispute" else "requested_at"
                self.assertGreaterEqual(
                    str(record[start_field])[:10],
                    str(accounts[record["account_id"]]["opened_at"])[:10],
                )
                self.assertLessEqual(str(record[start_field])[:10], AS_OF_DATE.isoformat())
                if record["status"] in {"resolved", "withdrawn", "approved", "declined"}:
                    self.assertIsNotNone(record["resolved_at"])
                else:
                    self.assertIsNone(record["resolved_at"])

    def test_payments_allocate_oldest_first_and_reconcile_unapplied_amount(self) -> None:
        dataset = generate_dataset(1_000, 92)
        payments = {row["payment_id"]: row for row in dataset["payment"]}
        installments = {
            row["installment_id"]: row for row in dataset["installment"]
        }
        loans = {row["loan_id"]: row for row in dataset["loan"]}
        allocations_by_payment: dict[str, list[dict[str, str | int | bool | None]]] = {}
        for allocation in dataset["payment_allocation"]:
            allocations_by_payment.setdefault(
                str(allocation["payment_id"]), []
            ).append(allocation)

        unapplied_total = 0
        for payment_id, payment in payments.items():
            allocations = allocations_by_payment.get(payment_id, [])
            allocation_sum = sum(int(row["allocated_amount"]) for row in allocations)
            unapplied = int(payment["unapplied_amount"])
            self.assertEqual(allocation_sum + unapplied, int(payment["amount"]))
            unapplied_total += unapplied
            due_dates = []
            for allocation in allocations:
                installment = installments[str(allocation["installment_id"])]
                loan = loans[str(installment["loan_id"])]
                self.assertEqual(loan["account_id"], payment["account_id"])
                due_dates.append(str(installment["due_date"]))
            if due_dates:
                self.assertEqual(due_dates, sorted(due_dates))
        self.assertGreater(unapplied_total, 0)

    def test_invalid_scale_is_rejected(self) -> None:
        for invalid in (0, -1, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    generate_dataset(invalid)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
