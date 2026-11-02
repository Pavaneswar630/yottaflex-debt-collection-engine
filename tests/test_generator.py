"""Tests for deterministic records, schedules, labels, and payment allocation."""

import csv
import hashlib
import unittest
from collections import Counter
from calendar import monthrange
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from yottaflex_debt_collection.generator import (
    CSV_COLUMNS,
    SEGMENT_PROBABILITIES,
    generate_dataset,
)
from yottaflex_debt_collection.schema_loader import load_dictionary
from yottaflex_debt_collection.settings import AS_OF_DATE


def _reference_delinquency(
    loan_id: str,
    as_of_date: date,
    installments: list[dict[str, str | int | bool | None]],
    allocations: list[dict[str, str | int | bool | None]],
    payments: list[dict[str, str | int | bool | None]],
) -> tuple[int, int]:
    """Deliberately slow, loop-based oracle independent of generator helpers."""
    arrears = 0
    oldest_unpaid_due_date: date | None = None
    for installment in installments:
        if installment["loan_id"] != loan_id:
            continue
        due_date = date.fromisoformat(str(installment["due_date"]))
        if due_date > as_of_date:
            continue
        paid = 0
        for allocation in allocations:
            if allocation["installment_id"] != installment["installment_id"]:
                continue
            for payment in payments:
                if payment["payment_id"] != allocation["payment_id"]:
                    continue
                if payment["status"] != "posted" or payment["posted_at"] is None:
                    continue
                posted_date = date.fromisoformat(str(payment["posted_at"])[:10])
                if posted_date <= as_of_date:
                    paid += int(allocation["allocated_amount"])
                break
        unpaid = max(0, int(installment["total_due"]) - paid)
        arrears += unpaid
        if unpaid and (
            oldest_unpaid_due_date is None or due_date < oldest_unpaid_due_date
        ):
            oldest_unpaid_due_date = due_date
    dpd = (
        (as_of_date - oldest_unpaid_due_date).days
        if oldest_unpaid_due_date is not None
        else 0
    )
    return arrears, dpd


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

    def test_snapshots_match_slow_reference_and_cover_required_dates(self) -> None:
        dataset = generate_dataset(80, 204)
        loans = {str(row["loan_id"]): row for row in dataset["loan"]}
        installments = dataset["installment"]
        allocations = dataset["payment_allocation"]
        payments = dataset["payment"]
        snapshots = dataset["delinquency_snapshot"]
        self.assertTrue(snapshots)

        snapshots_by_loan: dict[
            str, list[dict[str, str | int | bool | None]]
        ] = {}
        for snapshot in snapshots:
            loan_id = str(snapshot["loan_id"])
            snapshots_by_loan.setdefault(loan_id, []).append(snapshot)
            snapshot_date = date.fromisoformat(str(snapshot["snapshot_date"]))
            expected_arrears, expected_dpd = _reference_delinquency(
                loan_id, snapshot_date, installments, allocations, payments
            )
            self.assertEqual(int(snapshot["arrears_amount"]), expected_arrears)
            self.assertEqual(int(snapshot["days_past_due"]), expected_dpd)

        saw_case_open = False
        for loan_id, loan in loans.items():
            rows = snapshots_by_loan[loan_id]
            actual_reasons = {
                (str(row["snapshot_date"]), str(row["snapshot_reason"]))
                for row in rows
            }
            origination = date.fromisoformat(str(loan["origination_date"]))
            month = date(origination.year, origination.month, 1)
            while month <= AS_OF_DATE:
                end_of_month = date(
                    month.year,
                    month.month,
                    monthrange(month.year, month.month)[1],
                )
                if origination <= end_of_month <= AS_OF_DATE:
                    self.assertIn((end_of_month.isoformat(), "month_end"), actual_reasons)
                month_index = month.month
                year = month.year + (month_index // 12)
                month = date(year, month_index % 12 + 1, 1)

            self.assertIn((AS_OF_DATE.isoformat(), "as_of"), actual_reasons)
            due_dates = sorted(
                date.fromisoformat(str(row["due_date"]))
                for row in installments
                if row["loan_id"] == loan_id
                and date.fromisoformat(str(row["due_date"])) <= AS_OF_DATE
            )
            expected_case_open = next(
                (
                    due_date
                    for due_date in due_dates
                    if _reference_delinquency(
                        loan_id, due_date, installments, allocations, payments
                    )[0]
                    > 0
                ),
                None,
            )
            case_open_snapshots = [
                row for row in rows if row["snapshot_reason"] == "case_open"
            ]
            if expected_case_open is None:
                self.assertEqual(case_open_snapshots, [])
            else:
                saw_case_open = True
                self.assertEqual(len(case_open_snapshots), 1)
                self.assertEqual(
                    case_open_snapshots[0]["snapshot_date"],
                    expected_case_open.isoformat(),
                )
        self.assertTrue(saw_case_open)

    def test_invalid_scale_is_rejected(self) -> None:
        for invalid in (0, -1, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    generate_dataset(invalid)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
