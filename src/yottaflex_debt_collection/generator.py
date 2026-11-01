"""Reproducible, synthetic collection-data generation and CSV export."""

import csv
import math
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import TypeAlias
from zoneinfo import ZoneInfo

import numpy as np
from numpy.random import Generator

from yottaflex_debt_collection.ids import IdFactory
from yottaflex_debt_collection.rng import EntityRandomStreams
from yottaflex_debt_collection.settings import (
    AS_OF_DATE,
    DEFAULT_SEED,
    GENERATION_DATE,
    INSTALLMENTS_PER_LOAN,
)

Row: TypeAlias = dict[str, str | int | bool | None]
Dataset: TypeAlias = dict[str, list[Row]]

SEGMENT_PROBABILITIES = {
    "on_time": 0.55,
    "late_cure": 0.15,
    "partial": 0.10,
    "rolling": 0.08,
    "never_pay": 0.05,
    "early_payoff": 0.07,
}
SEGMENTS = tuple(SEGMENT_PROBABILITIES)
SEGMENT_WEIGHTS = tuple(SEGMENT_PROBABILITIES.values())
TIMEZONES = (
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Phoenix",
    "Pacific/Honolulu",
)
RISK_BANDS = ("low", "medium", "high", "critical")
RISK_WEIGHTS = (0.40, 0.35, 0.20, 0.05)
UTC_GENERATED_AT = f"{GENERATION_DATE.isoformat()}T12:00:00+00:00"
CSV_COLUMNS: dict[str, tuple[str, ...]] = {
    "customer": (
        "customer_id",
        "customer_type",
        "display_name",
        "risk_band",
        "timezone",
        "preferred_language",
        "created_at",
    ),
    "account": (
        "account_id",
        "customer_id",
        "account_status",
        "hardship_status",
        "opened_at",
        "closed_at",
    ),
    "loan": (
        "loan_id",
        "account_id",
        "product_type",
        "principal_amount",
        "currency",
        "annual_interest_rate",
        "term_months",
        "origination_date",
        "maturity_date",
        "loan_status",
        "paid_off_date",
    ),
    "installment": (
        "installment_id",
        "loan_id",
        "sequence_number",
        "due_date",
        "principal_due",
        "interest_due",
        "total_due",
        "installment_status",
        "created_at",
    ),
    "contact_preference": (
        "contact_preference_id",
        "account_id",
        "preferred_channel",
        "timezone",
        "allowed_start_time",
        "allowed_end_time",
        "do_not_contact",
        "effective_from",
        "effective_to",
        "created_at",
    ),
    "dispute": (
        "dispute_id",
        "account_id",
        "loan_id",
        "filed_at",
        "reason_code",
        "status",
        "resolved_at",
        "created_at",
    ),
    "hardship_request": (
        "hardship_request_id",
        "account_id",
        "loan_id",
        "requested_at",
        "reason_code",
        "status",
        "resolved_at",
        "created_at",
    ),
    "payment": (
        "payment_id",
        "account_id",
        "received_at",
        "posted_at",
        "amount",
        "unapplied_amount",
        "currency",
        "payment_method",
        "status",
        "external_reference",
        "created_at",
    ),
    "payment_allocation": (
        "payment_id",
        "installment_id",
        "allocated_amount",
        "allocated_at",
    ),
}


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _random_date(rng: Generator, start: date, end: date) -> date:
    days = (end - start).days
    return date.fromordinal(start.toordinal() + int(rng.integers(0, days + 1)))


def _timestamp(value: date) -> str:
    return f"{value.isoformat()}T12:00:00+00:00"


def _principal_schedule(principal: int, count: int) -> list[int]:
    regular_amount, remainder = divmod(principal, count)
    return [regular_amount] * (count - 1) + [regular_amount + remainder]


def _build_schedule(
    loan_id: str,
    principal: int,
    annual_rate_basis_points: int,
    origination_date: date,
    ids: IdFactory,
) -> list[Row]:
    rows: list[Row] = []
    for sequence, principal_due in enumerate(
        _principal_schedule(principal, INSTALLMENTS_PER_LOAN), start=1
    ):
        interest_due = (principal_due * annual_rate_basis_points + 20_000) // 40_000
        due_date = _add_months(origination_date, sequence * 4)
        rows.append(
            {
                "installment_id": ids.next_installment_id(loan_id),
                "loan_id": loan_id,
                "sequence_number": sequence,
                "due_date": due_date.isoformat(),
                "principal_due": principal_due,
                "interest_due": interest_due,
                "total_due": principal_due + interest_due,
                "installment_status": "scheduled",
                "created_at": UTC_GENERATED_AT,
            }
        )
    return rows


def _payment_events(
    segment: str, installments: list[Row], rng: Generator
) -> list[tuple[date, int]]:
    amounts = [int(row["total_due"]) for row in installments]
    due_dates = [date.fromisoformat(str(row["due_date"])) for row in installments]
    if segment == "never_pay":
        return []
    if segment == "early_payoff":
        return [(due_dates[0].fromordinal(due_dates[0].toordinal() - 30), sum(amounts))]

    events: list[tuple[date, int]] = []
    for due_date, amount in zip(due_dates, amounts):
        if segment == "on_time":
            received_date, payment_amount = due_date, amount
        elif segment == "late_cure":
            received_date, payment_amount = date.fromordinal(due_date.toordinal() + 30), amount
        elif segment == "partial":
            received_date = date.fromordinal(due_date.toordinal() + 5)
            payment_amount = amount * int(rng.integers(50, 81)) // 100
        else:
            received_date = date.fromordinal(due_date.toordinal() + 60)
            payment_amount = amount * int(rng.integers(60, 81)) // 100
        events.append((received_date, max(payment_amount, 1)))
    return events


def generate_dataset(
    loans: int = 10_000,
    seed: int = DEFAULT_SEED,
    output_dir: Path | str | None = None,
) -> Dataset:
    """Generate synthetic records, optionally writing CSVs under ``output_dir``.

    CSV tables are written to ``data/`` and the label-only segment file to
    ``ground_truth/latent_segments.csv``. No customer PII or external data is used.
    """
    if isinstance(loans, bool) or not isinstance(loans, int) or loans < 1:
        raise ValueError("loans must be a positive integer")
    streams = EntityRandomStreams(seed)
    ids = IdFactory()
    customer_rng = streams.for_entity("customer")
    account_rng = streams.for_entity("account")
    loan_rng = streams.for_entity("loan")
    preference_rng = streams.for_entity("contact_preference")
    payment_rng = streams.for_entity("payment")
    ground_truth_rng = streams.for_entity("ground_truth")
    hardship_rng = streams.for_entity("hardship_request")
    dispute_rng = streams.for_entity("dispute")

    customer_count = math.ceil(loans / 2)
    customer_ids = [ids.next_id("customer") for _ in range(customer_count)]
    customers: list[Row] = []
    customer_timezone: dict[str, str] = {}
    for customer_id in customer_ids:
        risk = str(customer_rng.choice(RISK_BANDS, p=RISK_WEIGHTS))
        timezone = str(customer_rng.choice(TIMEZONES))
        ZoneInfo(timezone)
        customer_timezone[customer_id] = timezone
        customers.append(
            {
                "customer_id": customer_id,
                "customer_type": "individual",
                "display_name": f"Synthetic Customer {customer_id[-6:]}",
                "risk_band": risk,
                "timezone": timezone,
                "preferred_language": "en-US",
                "created_at": UTC_GENERATED_AT,
            }
        )

    accounts: list[Row] = []
    account_ids: list[str] = []
    account_customer: dict[str, str] = {}
    account_opened: dict[str, date] = {}
    for index in range(loans):
        account_id = ids.next_id("account")
        customer_id = customer_ids[index % customer_count]
        opened_at = _random_date(account_rng, date(2025, 1, 1), date(2025, 8, 31))
        account_ids.append(account_id)
        account_customer[account_id] = customer_id
        account_opened[account_id] = opened_at
        accounts.append(
            {
                "account_id": account_id,
                "customer_id": customer_id,
                "account_status": "open",
                "hardship_status": "none",
                "opened_at": _timestamp(opened_at),
                "closed_at": None,
            }
        )

    segment_labels = [
        str(value)
        for value in ground_truth_rng.choice(
            SEGMENTS, size=loans, p=SEGMENT_WEIGHTS
        )
    ]
    loans_rows: list[Row] = []
    installments: list[Row] = []
    installments_by_loan: dict[str, list[Row]] = {}
    segment_by_loan: dict[str, str] = {}
    loan_account: dict[str, str] = {}
    for index, (account_id, segment) in enumerate(zip(account_ids, segment_labels)):
        loan_id = ids.next_id("loan")
        principal = int(loan_rng.integers(100_000, 2_000_001))
        annual_rate_basis_points = int(loan_rng.integers(500, 2_001))
        origination_date = account_opened[account_id]
        schedule = _build_schedule(
            loan_id, principal, annual_rate_basis_points, origination_date, ids
        )
        installments.extend(schedule)
        installments_by_loan[loan_id] = schedule
        segment_by_loan[loan_id] = segment
        loan_account[loan_id] = account_id
        loans_rows.append(
            {
                "loan_id": loan_id,
                "account_id": account_id,
                "product_type": str(
                    loan_rng.choice(("personal", "auto", "mortgage", "credit_line"))
                ),
                "principal_amount": principal,
                "currency": "USD",
                "annual_interest_rate": f"{annual_rate_basis_points / 100:.4f}",
                "term_months": INSTALLMENTS_PER_LOAN * 4,
                "origination_date": origination_date.isoformat(),
                "maturity_date": str(schedule[-1]["due_date"]),
                "loan_status": "active",
                "paid_off_date": None,
            }
        )

    contact_preferences: list[Row] = []
    for account_id in account_ids:
        start_hour = int(preference_rng.integers(8, 11))
        end_hour = int(preference_rng.integers(17, 20))
        contact_preferences.append(
            {
                "contact_preference_id": ids.next_id("contact_preference"),
                "account_id": account_id,
                "preferred_channel": str(
                    preference_rng.choice(("phone", "email", "sms", "postal"))
                ),
                "timezone": customer_timezone[account_customer[account_id]],
                "allowed_start_time": f"{start_hour:02d}:00:00",
                "allowed_end_time": f"{end_hour:02d}:00:00",
                "do_not_contact": bool(preference_rng.random() < 0.10),
                "effective_from": account_opened[account_id].isoformat(),
                "effective_to": None,
                "created_at": UTC_GENERATED_AT,
            }
        )

    disputes: list[Row] = []
    hardship_requests: list[Row] = []
    loan_by_account = {str(row["account_id"]): str(row["loan_id"]) for row in loans_rows}
    for account in accounts:
        account_id = str(account["account_id"])
        loan_id = loan_by_account[account_id]
        opened_at = account_opened[account_id]
        if dispute_rng.random() < 0.04:
            filed_at = _random_date(dispute_rng, opened_at, AS_OF_DATE)
            status = str(dispute_rng.choice(("under_review", "resolved", "withdrawn")))
            resolved_at = (
                _timestamp(
                    min(
                        AS_OF_DATE,
                        date.fromordinal(
                            filed_at.toordinal()
                            + int(dispute_rng.integers(5, 61))
                        ),
                    )
                )
                if status != "under_review"
                else None
            )
            disputes.append(
                {
                    "dispute_id": ids.next_id("dispute"),
                    "account_id": account_id,
                    "loan_id": loan_id,
                    "filed_at": _timestamp(filed_at),
                    "reason_code": str(
                        dispute_rng.choice(
                            ("balance_question", "payment_not_posted", "identity_question")
                        )
                    ),
                    "status": status,
                    "resolved_at": resolved_at,
                    "created_at": UTC_GENERATED_AT,
                }
            )
        if hardship_rng.random() < 0.08:
            requested_at = _random_date(hardship_rng, opened_at, AS_OF_DATE)
            status = str(hardship_rng.choice(("requested", "approved", "declined")))
            resolved_at = (
                _timestamp(
                    min(
                        AS_OF_DATE,
                        date.fromordinal(
                            requested_at.toordinal()
                            + int(hardship_rng.integers(5, 61))
                        ),
                    )
                )
                if status != "requested"
                else None
            )
            hardship_requests.append(
                {
                    "hardship_request_id": ids.next_id("hardship_request"),
                    "account_id": account_id,
                    "loan_id": loan_id,
                    "requested_at": _timestamp(requested_at),
                    "reason_code": str(
                        hardship_rng.choice(
                            ("income_loss", "medical", "disaster", "other")
                        )
                    ),
                    "status": status,
                    "resolved_at": resolved_at,
                    "created_at": UTC_GENERATED_AT,
                }
            )
            account["hardship_status"] = status

    payment_events: list[tuple[date, str, str, int]] = []
    for loan_id, schedule in installments_by_loan.items():
        for received_at, amount in _payment_events(
            segment_by_loan[loan_id], schedule, payment_rng
        ):
            if payment_rng.random() < 0.02:
                amount += int(payment_rng.integers(1, 501))
            payment_events.append(
                (received_at, loan_account[loan_id], loan_id, amount)
            )
    payment_events.sort(key=lambda event: (event[1], event[0], event[2]))

    outstanding = {
        str(row["installment_id"]): int(row["total_due"]) for row in installments
    }
    installments_for_account: dict[str, list[Row]] = {}
    for row in installments:
        account_id = loan_account[str(row["loan_id"])]
        installments_for_account.setdefault(account_id, []).append(row)
    for rows in installments_for_account.values():
        rows.sort(key=lambda row: (str(row["due_date"]), int(row["sequence_number"])))

    payments: list[Row] = []
    allocations: list[Row] = []
    allocation_totals: dict[str, int] = {}
    last_payment_by_loan: dict[str, date] = {}
    for event_index, (received_at, account_id, _source_loan, amount) in enumerate(
        payment_events, start=1
    ):
        payment_id = ids.next_id("payment")
        remaining = amount
        for installment in installments_for_account[account_id]:
            installment_id = str(installment["installment_id"])
            available = outstanding[installment_id]
            allocated = min(available, remaining)
            if allocated == 0:
                continue
            allocations.append(
                {
                    "payment_id": payment_id,
                    "installment_id": installment_id,
                    "allocated_amount": allocated,
                    "allocated_at": _timestamp(received_at),
                }
            )
            outstanding[installment_id] -= allocated
            allocation_totals[installment_id] = (
                allocation_totals.get(installment_id, 0) + allocated
            )
            last_payment_by_loan[str(installment["loan_id"])] = received_at
            remaining -= allocated
            if remaining == 0:
                break

        received_timestamp = _timestamp(received_at)
        payments.append(
            {
                "payment_id": payment_id,
                "account_id": account_id,
                "received_at": received_timestamp,
                "posted_at": received_timestamp,
                "amount": amount,
                "unapplied_amount": remaining,
                "currency": "USD",
                "payment_method": str(
                    payment_rng.choice(
                        ("bank_transfer", "card", "cash", "direct_debit", "other")
                    )
                ),
                "status": "posted",
                "external_reference": f"SYN-{event_index:08d}",
                "created_at": UTC_GENERATED_AT,
            }
        )

    for installment in installments:
        installment_id = str(installment["installment_id"])
        due_date = date.fromisoformat(str(installment["due_date"]))
        total_due = int(installment["total_due"])
        paid = allocation_totals.get(installment_id, 0)
        if paid >= total_due:
            installment["installment_status"] = "paid"
        elif paid > 0:
            installment["installment_status"] = "partially_paid"
        elif due_date <= AS_OF_DATE:
            installment["installment_status"] = "past_due"
        else:
            installment["installment_status"] = "scheduled"

    for loan in loans_rows:
        loan_id = str(loan["loan_id"])
        remaining = sum(
            outstanding[str(row["installment_id"])]
            for row in installments_by_loan[loan_id]
        )
        if remaining == 0:
            loan["loan_status"] = "paid_off"
            loan["paid_off_date"] = last_payment_by_loan[loan_id].isoformat()

    dataset: Dataset = {
        "customer": customers,
        "account": accounts,
        "loan": loans_rows,
        "installment": installments,
        "contact_preference": contact_preferences,
        "dispute": disputes,
        "hardship_request": hardship_requests,
        "payment": payments,
        "payment_allocation": allocations,
        "latent_segments": [
            {"loan_id": loan_id, "segment": segment_by_loan[loan_id]}
            for loan_id in (str(row["loan_id"]) for row in loans_rows)
        ],
    }
    validate_dataset(dataset)
    if output_dir is not None:
        write_dataset(dataset, Path(output_dir))
    return dataset


def validate_dataset(dataset: Dataset) -> None:
    """Validate generated identifiers, joins, schedules, and payment reconciliation."""
    id_fields = {
        "customer": "customer_id",
        "account": "account_id",
        "loan": "loan_id",
        "installment": "installment_id",
        "contact_preference": "contact_preference_id",
        "dispute": "dispute_id",
        "hardship_request": "hardship_request_id",
        "payment": "payment_id",
    }
    for table, field in id_fields.items():
        ids = [str(row[field]) for row in dataset[table]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{table} primary keys are not unique")

    customer_ids = {str(row["customer_id"]) for row in dataset["customer"]}
    account_ids = {str(row["account_id"]) for row in dataset["account"]}
    loan_ids = {str(row["loan_id"]) for row in dataset["loan"]}
    payment_ids = {str(row["payment_id"]) for row in dataset["payment"]}
    loans_by_id = {str(row["loan_id"]): row for row in dataset["loan"]}
    accounts_by_id = {str(row["account_id"]): row for row in dataset["account"]}
    customers_by_id = {str(row["customer_id"]): row for row in dataset["customer"]}
    for row in dataset["loan"]:
        if str(row["account_id"]) not in account_ids:
            raise ValueError("loan references an unknown account")
    for row in dataset["account"]:
        if str(row["customer_id"]) not in customers_by_id:
            raise ValueError("account references an unknown customer")
    installments_by_id: dict[str, Row] = {}
    grouped_installments: dict[str, list[Row]] = {}
    for row in dataset["installment"]:
        loan_id = str(row["loan_id"])
        if loan_id not in loan_ids:
            raise ValueError("installment references an unknown loan")
        installment_id = str(row["installment_id"])
        if installment_id in installments_by_id:
            raise ValueError("installment primary keys are not unique")
        installments_by_id[installment_id] = row
        if int(row["total_due"]) != int(row["principal_due"]) + int(row["interest_due"]):
            raise ValueError("installment amount does not reconcile")
        grouped_installments.setdefault(loan_id, []).append(row)
    for loan_id, rows in grouped_installments.items():
        rows.sort(key=lambda row: int(row["sequence_number"]))
        if len(rows) != INSTALLMENTS_PER_LOAN:
            raise ValueError(f"{loan_id} does not have the configured installment count")
        if [int(row["sequence_number"]) for row in rows] != list(
            range(1, INSTALLMENTS_PER_LOAN + 1)
        ):
            raise ValueError(f"{loan_id} installment sequence is invalid")
        if [str(row["due_date"]) for row in rows] != sorted(
            str(row["due_date"]) for row in rows
        ):
            raise ValueError(f"{loan_id} installment due dates are not ordered")
        if sum(int(row["principal_due"]) for row in rows) != int(
            loans_by_id[loan_id]["principal_amount"]
        ):
            raise ValueError(f"{loan_id} principal schedule does not reconcile")

    preference_account_ids = {str(row["account_id"]) for row in dataset["contact_preference"]}
    if preference_account_ids != account_ids:
        raise ValueError("each account must have one contact preference")
    for row in dataset["contact_preference"]:
        if str(row["account_id"]) not in account_ids:
            raise ValueError("contact preference references an unknown account")
        account_customer_id = str(accounts_by_id[str(row["account_id"])]["customer_id"])
        if row["timezone"] != customers_by_id[account_customer_id]["timezone"]:
            raise ValueError("contact preference timezone does not match its customer")
        if not "08:00:00" <= str(row["allowed_start_time"]) < str(
            row["allowed_end_time"]
        ) <= "19:00:00":
            raise ValueError("contact preference is outside the permitted local window")

    for table in ("dispute", "hardship_request"):
        for row in dataset[table]:
            account_id = str(row["account_id"])
            loan_id = str(row["loan_id"])
            if account_id not in account_ids or loan_id not in loan_ids:
                raise ValueError(f"{table} references an unknown parent")
            if str(loans_by_id[loan_id]["account_id"]) != account_id:
                raise ValueError(f"{table} account does not own its referenced loan")

    payment_account = {
        str(row["payment_id"]): str(row["account_id"]) for row in dataset["payment"]
    }
    if len(payment_account) != len(dataset["payment"]):
        raise ValueError("payment primary keys are not unique")
    allocation_pairs: set[tuple[str, str]] = set()
    allocations_by_payment: dict[str, list[Row]] = {}
    allocation_sums: dict[str, int] = {}
    for row in dataset["payment_allocation"]:
        payment_id = str(row["payment_id"])
        installment_id = str(row["installment_id"])
        if payment_id not in payment_ids or installment_id not in installments_by_id:
            raise ValueError("payment allocation references an unknown parent")
        pair = (payment_id, installment_id)
        if pair in allocation_pairs:
            raise ValueError("duplicate payment-installment allocation")
        allocation_pairs.add(pair)
        installment = installments_by_id[installment_id]
        loan = loans_by_id[str(installment["loan_id"])]
        if str(loan["account_id"]) != payment_account[payment_id]:
            raise ValueError("payment was allocated outside its account")
        if int(row["allocated_amount"]) <= 0:
            raise ValueError("payment allocation must be positive")
        allocations_by_payment.setdefault(payment_id, []).append(row)
        allocation_sums[payment_id] = (
            allocation_sums.get(payment_id, 0) + int(row["allocated_amount"])
        )

    balances = {
        installment_id: int(row["total_due"])
        for installment_id, row in installments_by_id.items()
    }
    installments_by_account: dict[str, list[Row]] = {}
    for installment in dataset["installment"]:
        loan = loans_by_id[str(installment["loan_id"])]
        installments_by_account.setdefault(str(loan["account_id"]), []).append(
            installment
        )
    for rows in installments_by_account.values():
        rows.sort(key=lambda row: (str(row["due_date"]), int(row["sequence_number"])))

    payments_by_date = sorted(
        dataset["payment"],
        key=lambda row: (str(row["received_at"]), str(row["payment_id"])),
    )
    for payment in payments_by_date:
        payment_id = str(payment["payment_id"])
        account_id = str(payment["account_id"])
        if account_id not in account_ids:
            raise ValueError("payment references an unknown account")
        if str(payment["currency"]) != "USD":
            raise ValueError("generated payment currency must be USD")
        amount = int(payment["amount"])
        if amount <= 0:
            raise ValueError("payment amount must be positive")
        remaining = amount
        expected_allocations: list[tuple[str, int]] = []
        for installment in installments_by_account[account_id]:
            installment_id = str(installment["installment_id"])
            allocated = min(balances[installment_id], remaining)
            if allocated > 0:
                expected_allocations.append((installment_id, allocated))
                balances[installment_id] -= allocated
                remaining -= allocated
            if remaining == 0:
                break
        actual_allocations = [
            (str(row["installment_id"]), int(row["allocated_amount"]))
            for row in allocations_by_payment.get(payment_id, [])
        ]
        if actual_allocations != expected_allocations:
            raise ValueError("payment allocations are not oldest-first")
        if (
            allocation_sums.get(payment_id, 0) + int(payment["unapplied_amount"])
            != amount
        ):
            raise ValueError("payment allocations and unapplied amount do not reconcile")
    if any(
        str(row["account_id"]) not in accounts_by_id
        for table in ("contact_preference", "dispute", "hardship_request")
        for row in dataset[table]
    ):
        raise ValueError("account-scoped record references an unknown account")
    if any(
        segment not in SEGMENTS
        for segment in (row["segment"] for row in dataset["latent_segments"])
    ):
        raise ValueError("unknown latent behavior segment")
    label_loan_ids = [str(row["loan_id"]) for row in dataset["latent_segments"]]
    if len(label_loan_ids) != len(set(label_loan_ids)) or set(label_loan_ids) != loan_ids:
        raise ValueError("ground-truth labels must contain each loan exactly once")


def write_dataset(dataset: Dataset, output_dir: Path) -> None:
    """Write stable UTF-8 CSVs, keeping latent labels outside model input tables."""
    data_dir = output_dir / "data"
    ground_truth_dir = output_dir / "ground_truth"
    data_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_dir.mkdir(parents=True, exist_ok=True)
    for table, columns in CSV_COLUMNS.items():
        path = data_dir / f"{table}.csv"
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(dataset[table])
    with (ground_truth_dir / "latent_segments.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.DictWriter(
            output, fieldnames=("loan_id", "segment"), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(dataset["latent_segments"])
