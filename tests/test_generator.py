"""Tests for deterministic records, schedules, labels, and payment allocation."""

import csv
import copy
import hashlib
import unittest
from collections import Counter
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import yaml

from yottaflex_debt_collection.generator import (
    CSV_COLUMNS,
    SEGMENT_PROBABILITIES,
    _first_matching_suppression_rule,
    _promise_outcome,
    _schedule_contact_decision,
    generate_dataset,
    validate_dataset,
)
from yottaflex_debt_collection.schema_loader import load_dictionary
from yottaflex_debt_collection.settings import AS_OF_DATE

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load(
    (ROOT / "config" / "policy.yaml").read_text(encoding="utf-8")
)


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
        self.assertEqual(
            {row["priority_tier"] for row in dataset["collection_case"]},
            {"P1", "P2", "P3"},
        )
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
        loan_accounts = {
            str(row["loan_id"]): str(row["account_id"])
            for row in dataset["loan"]
        }
        installments_by_loan: dict[
            str, list[dict[str, str | int | bool | None]]
        ] = {}
        for installment in installments:
            installments_by_loan.setdefault(str(installment["loan_id"]), []).append(
                installment
            )
        allocations_by_loan: dict[
            str, list[dict[str, str | int | bool | None]]
        ] = {}
        for allocation in allocations:
            allocation_loan_id = next(
                str(installment["loan_id"])
                for installment in installments
                if installment["installment_id"] == allocation["installment_id"]
            )
            allocations_by_loan.setdefault(allocation_loan_id, []).append(allocation)
        payments_by_account: dict[
            str, list[dict[str, str | int | bool | None]]
        ] = {}
        for payment in payments:
            payments_by_account.setdefault(str(payment["account_id"]), []).append(payment)

        snapshots_by_loan: dict[
            str, list[dict[str, str | int | bool | None]]
        ] = {}
        for snapshot in snapshots:
            loan_id = str(snapshot["loan_id"])
            snapshots_by_loan.setdefault(loan_id, []).append(snapshot)
            snapshot_date = date.fromisoformat(str(snapshot["snapshot_date"]))
            expected_arrears, expected_dpd = _reference_delinquency(
                loan_id,
                snapshot_date,
                installments_by_loan[loan_id],
                allocations_by_loan.get(loan_id, []),
                payments_by_account.get(loan_accounts[loan_id], []),
            )
            self.assertEqual(int(snapshot["arrears_amount"]), expected_arrears)
            self.assertEqual(int(snapshot["days_past_due"]), expected_dpd)

        saw_case_open = False
        for loan_id, loan in loans.items():
            rows = snapshots_by_loan[loan_id]
            loan_installments = installments_by_loan[loan_id]
            loan_allocations = allocations_by_loan.get(loan_id, [])
            loan_payments = payments_by_account.get(loan_accounts[loan_id], [])
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
                for row in loan_installments
                if date.fromisoformat(str(row["due_date"])) <= AS_OF_DATE
            )
            expected_case_open = None
            if due_dates:
                candidate = due_dates[0]
                while candidate <= AS_OF_DATE:
                    _, dpd = _reference_delinquency(
                        loan_id,
                        candidate,
                        loan_installments,
                        loan_allocations,
                        loan_payments,
                    )
                    if dpd >= POLICY["rules"]["R-CASE-01"]["dpd_threshold"]:
                        expected_case_open = candidate
                        break
                    candidate += date.resolution
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

    def test_cases_open_at_first_dpd_threshold_and_store_explainable_scores(self) -> None:
        dataset = generate_dataset(120, 310)
        threshold = POLICY["rules"]["R-CASE-01"]["dpd_threshold"]
        loans = {str(row["loan_id"]): row for row in dataset["loan"]}
        customers = {str(row["customer_id"]): row for row in dataset["customer"]}
        accounts = {str(row["account_id"]): row for row in dataset["account"]}
        installments = dataset["installment"]
        allocations = dataset["payment_allocation"]
        payments = dataset["payment"]
        cases_by_loan = {str(row["loan_id"]): row for row in dataset["collection_case"]}

        for loan_id, loan in loans.items():
            loan_installments = [
                row for row in installments if row["loan_id"] == loan_id
            ]
            loan_installment_ids = {
                str(row["installment_id"]) for row in loan_installments
            }
            loan_allocations = [
                row
                for row in allocations
                if row["installment_id"] in loan_installment_ids
            ]
            loan_account_id = str(loan["account_id"])
            loan_payments = [
                row for row in payments if row["account_id"] == loan_account_id
            ]
            earliest_due = min(
                date.fromisoformat(str(row["due_date"])) for row in loan_installments
            )
            expected_open_date = None
            candidate = earliest_due
            while candidate <= AS_OF_DATE:
                _, dpd = _reference_delinquency(
                    loan_id, candidate, loan_installments, loan_allocations, loan_payments
                )
                if dpd >= threshold:
                    expected_open_date = candidate
                    break
                candidate += date.resolution

            case = cases_by_loan.get(loan_id)
            if expected_open_date is None:
                self.assertIsNone(case)
                continue
            self.assertIsNotNone(case)
            assert case is not None
            self.assertEqual(
                str(case["opened_at"])[:10], expected_open_date.isoformat()
            )

            arrears, dpd = _reference_delinquency(
                loan_id, AS_OF_DATE, loan_installments, loan_allocations, loan_payments
            )
            self.assertEqual(case["scored_at"], AS_OF_DATE.isoformat())
            account = accounts[str(loan["account_id"])]
            customer = customers[str(account["customer_id"])]
            risk_band = str(customer["risk_band"])
            risk_score_by_band = {"low": 20, "medium": 45, "high": 70, "critical": 90}
            balance_component = min(arrears / int(loan["principal_amount"]), 1.0)
            age_bucket = next(
                bucket
                for bucket in POLICY["scoring"]["dpd_buckets"]
                if dpd >= bucket["min_days"]
                and (bucket["max_days"] is None or dpd <= bucket["max_days"])
            )
            age_component = age_bucket["score"] / 100
            risk_component = risk_score_by_band[risk_band] / 100
            expected_score = round(
                100
                * (
                    POLICY["scoring"]["w_balance"] * round(balance_component, 4)
                    + POLICY["scoring"]["w_age"] * age_component
                    + POLICY["scoring"]["w_risk"] * risk_component
                ),
                2,
            )
            self.assertAlmostEqual(
                float(case["balance_component"]), balance_component, places=4
            )
            self.assertAlmostEqual(
                float(case["age_component"]), age_component, places=4
            )
            self.assertAlmostEqual(
                float(case["risk_component"]), risk_component, places=4
            )
            self.assertEqual(float(case["priority_score"]), expected_score)
            expected_tier = (
                "P1"
                if expected_score >= POLICY["scoring"]["tiers"]["p1_min_score"]
                else "P2"
                if expected_score >= POLICY["scoring"]["tiers"]["p2_min_score"]
                else "P3"
            )
            self.assertEqual(case["priority_tier"], expected_tier)
            for reason_code in (
                "CASE_DPD_THRESHOLD_CROSSED",
                f"AGE_{age_bucket['name'].upper()}",
                f"RISK_{risk_band.upper()}",
            ):
                self.assertIn(reason_code, str(case["reason_codes"]))

    def test_suppression_uses_first_matching_policy_rule(self) -> None:
        loan = {"loan_status": "paid_off"}
        account = {"hardship_status": "approved"}
        disputes = [
            {
                "status": "under_review",
                "filed_at": "2026-10-01T12:00:00+00:00",
                "resolved_at": None,
            }
        ]
        hardship_requests = [
            {
                "status": "requested",
                "requested_at": "2026-10-01T12:00:00+00:00",
            }
        ]
        contact_preference = {
            "do_not_contact": True,
            "effective_from": "2026-01-01",
            "effective_to": None,
        }

        self.assertEqual(
            _first_matching_suppression_rule(
                loan,
                account,
                disputes,
                hardship_requests,
                contact_preference,
                AS_OF_DATE,
                POLICY,
            ),
            "R-PAIDOFF-01",
        )
        loan["loan_status"] = "active"
        self.assertEqual(
            _first_matching_suppression_rule(
                loan,
                account,
                disputes,
                hardship_requests,
                contact_preference,
                AS_OF_DATE,
                POLICY,
            ),
            "R-DISPUTE-01",
        )
        disputes.clear()
        self.assertEqual(
            _first_matching_suppression_rule(
                loan,
                account,
                disputes,
                hardship_requests,
                contact_preference,
                AS_OF_DATE,
                POLICY,
            ),
            "R-HARDSHIP-01",
        )
        hardship_requests.clear()
        account["hardship_status"] = "none"
        self.assertEqual(
            _first_matching_suppression_rule(
                loan,
                account,
                disputes,
                hardship_requests,
                contact_preference,
                AS_OF_DATE,
                POLICY,
            ),
            "R-CEASE-01",
        )
        contact_preference["do_not_contact"] = False
        self.assertIsNone(
            _first_matching_suppression_rule(
                loan,
                account,
                disputes,
                hardship_requests,
                contact_preference,
                AS_OF_DATE,
                POLICY,
            )
        )

    def test_each_case_has_one_scheduled_blocked_or_suppressed_decision(self) -> None:
        dataset = generate_dataset(500, 217)
        decisions_by_case: dict[str, list[dict[str, str | int | bool | None]]] = {}
        for decision in dataset["decision_log"]:
            decisions_by_case.setdefault(str(decision["case_id"]), []).append(decision)
            self.assertTrue(decision["rule_id"])

        self.assertEqual(set(decisions_by_case), {row["case_id"] for row in dataset["collection_case"]})
        cases_by_id = {str(row["case_id"]): row for row in dataset["collection_case"]}
        for case in dataset["collection_case"]:
            decisions = decisions_by_case[str(case["case_id"])]
            self.assertEqual(len(decisions), 1)
            decision = decisions[0]
            self.assertEqual(decision["loan_id"], cases_by_id[str(case["case_id"])]["loan_id"])
            if case["suppression_rule_id"] is not None:
                self.assertEqual(decision["rule_id"], case["suppression_rule_id"])
                self.assertIn("suppressed", str(decision["reason"]))
                self.assertIsNone(case["next_action_at"])
            elif decision["decision_type"] == "contact_allowed":
                self.assertEqual(decision["rule_id"], "R-CONTACT-01")
                self.assertEqual(decision["outcome"], "allow")
                self.assertIsNotNone(case["next_action_at"])
            else:
                self.assertEqual(decision["decision_type"], "contact_blocked")
                self.assertEqual(decision["outcome"], "block")
                self.assertIsNotNone(decision["rule_id"])
                self.assertIsNone(case["next_action_at"])

    def test_contact_scheduler_enforces_window_restriction_and_weekly_cap(self) -> None:
        base_case = {
            "case_id": "COL-2026-000001",
            "account_id": "ACC-000001",
            "loan_id": "LOAN-2026-000001",
            "priority_score": "55.00",
            "suppression_rule_id": None,
        }
        preference = {
            "account_id": "ACC-000001",
            "timezone": "America/New_York",
            "allowed_start_time": "08:00:00",
            "allowed_end_time": "19:00:00",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "do_not_contact": False,
        }

        restricted_preference = {**preference, "do_not_contact": True}
        restricted_decision, restricted_schedule = _schedule_contact_decision(
            base_case,
            restricted_preference,
            "DEC-2026-000001",
            POLICY,
            [],
        )
        self.assertEqual(restricted_decision["rule_id"], "R-CEASE-01")
        self.assertEqual(restricted_decision["outcome"], "block")
        self.assertIsNone(restricted_schedule)

        out_of_window_preference = {
            **preference,
            "allowed_start_time": "20:00:00",
            "allowed_end_time": "21:00:00",
        }
        window_decision, window_schedule = _schedule_contact_decision(
            base_case,
            out_of_window_preference,
            "DEC-2026-000002",
            POLICY,
            [],
        )
        self.assertEqual(window_decision["rule_id"], "R-CONTACT-01")
        self.assertEqual(window_decision["outcome"], "block")
        self.assertIsNone(window_schedule)

        scheduled_history = [
            (
                "ACC-000001",
                datetime(2026, 10, 28, 8, 0, tzinfo=ZoneInfo("America/New_York")),
            )
            for _ in range(POLICY["rules"]["R-CONTACT-02"]["max_attempts"])
        ]
        cap_decision, cap_schedule = _schedule_contact_decision(
            base_case,
            preference,
            "DEC-2026-000003",
            POLICY,
            scheduled_history,
        )
        self.assertEqual(cap_decision["rule_id"], "R-CONTACT-02")
        self.assertEqual(cap_decision["outcome"], "block")
        self.assertIsNone(cap_schedule)

        allowed_decision, allowed_schedule = _schedule_contact_decision(
            base_case,
            preference,
            "DEC-2026-000004",
            POLICY,
            [],
        )
        self.assertEqual(allowed_decision["rule_id"], "R-CONTACT-01")
        self.assertEqual(allowed_decision["outcome"], "allow")
        self.assertIsNotNone(allowed_schedule)
        assert allowed_schedule is not None
        self.assertEqual(allowed_schedule.tzinfo, ZoneInfo("America/New_York"))
        self.assertEqual(allowed_schedule.hour, 8)

    def test_contact_promises_reconciliation_and_state_lifecycles(self) -> None:
        dataset = generate_dataset(1_000, 20261022)
        self.assertEqual(
            {row["status"] for row in dataset["promise_to_pay"]},
            {"KEPT", "PARTIAL", "BROKEN"},
        )
        self.assertEqual(
            {row["outcome"] for row in dataset["contact_attempt"]},
            {"connected", "no_answer", "voicemail", "refused", "policy_blocked"},
        )

        attempts_by_case = {
            str(row["case_id"]): row for row in dataset["contact_attempt"]
        }
        promises_by_case = {
            str(row["case_id"]): row for row in dataset["promise_to_pay"]
        }
        for case in dataset["collection_case"]:
            attempt = attempts_by_case[str(case["case_id"])]
            promise = promises_by_case.get(str(case["case_id"]))
            if attempt["outcome"] == "connected":
                if promise is not None:
                    arrears_at_promise, _ = _reference_delinquency(
                        str(case["loan_id"]),
                        datetime.fromisoformat(str(promise["recorded_at"])).date(),
                        dataset["installment"],
                        dataset["payment_allocation"],
                        dataset["payment"],
                    )
                    expected_amount = max(1, arrears_at_promise * 70 // 100)
                    self.assertEqual(int(promise["promised_amount"]), expected_amount)
            else:
                self.assertIsNone(promise)

        state_rows_by_promise: dict[str, list[dict[str, str | int | bool | None]]] = {}
        for event in dataset["state_event"]:
            if event["entity_type"] == "promise_to_pay":
                state_rows_by_promise.setdefault(str(event["promise_id"]), []).append(event)
        for promise in dataset["promise_to_pay"]:
            events = state_rows_by_promise[str(promise["promise_id"])]
            self.assertEqual(events[0]["new_state"], "PENDING")
            self.assertEqual(events[-1]["new_state"], promise["status"])

        corrupted = copy.deepcopy(dataset)
        transition = next(
            event
            for event in corrupted["state_event"]
            if event["entity_type"] == "promise_to_pay"
            and event["previous_state"] == "PENDING"
        )
        transition["previous_state"] = "BROKEN"
        with self.assertRaisesRegex(ValueError, "previous_state"):
            validate_dataset(corrupted)

    def test_promise_outcome_uses_exact_tolerance_boundary(self) -> None:
        self.assertEqual(_promise_outcome(9_500, 10_000, 5), "KEPT")
        self.assertEqual(_promise_outcome(9_499, 10_000, 5), "PARTIAL")
        self.assertEqual(_promise_outcome(1, 10_000, 5), "PARTIAL")
        self.assertEqual(_promise_outcome(0, 10_000, 5), "BROKEN")

    def test_invalid_scale_is_rejected(self) -> None:
        for invalid in (0, -1, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    generate_dataset(invalid)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
