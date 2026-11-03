"""Structural integrity checks for exported collection datasets."""

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Sequence


PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "customer": ("customer_id",),
    "account": ("account_id",),
    "loan": ("loan_id",),
    "installment": ("installment_id",),
    "delinquency_snapshot": ("snapshot_id",),
    "collection_case": ("case_id",),
    "contact_preference": ("contact_preference_id",),
    "dispute": ("dispute_id",),
    "hardship_request": ("hardship_request_id",),
    "payment": ("payment_id",),
    "payment_allocation": ("payment_id", "installment_id"),
    "decision_log": ("decision_id",),
    "contact_attempt": ("contact_attempt_id",),
    "promise_to_pay": ("promise_id",),
    "promise_reconciliation": ("promise_id", "payment_id"),
    "state_event": ("state_event_id",),
}

REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "customer": frozenset({"customer_id", "customer_type", "risk_band", "created_at"}),
    "account": frozenset(
        {"account_id", "customer_id", "account_status", "opened_at", "closed_at"}
    ),
    "loan": frozenset(
        {
            "loan_id",
            "account_id",
            "principal_amount",
            "loan_status",
            "origination_date",
            "maturity_date",
            "paid_off_date",
        }
    ),
    "installment": frozenset(
        {
            "installment_id",
            "loan_id",
            "sequence_number",
            "due_date",
            "principal_due",
            "interest_due",
            "total_due",
            "installment_status",
            "created_at",
        }
    ),
    "delinquency_snapshot": frozenset(
        {
            "snapshot_id",
            "loan_id",
            "snapshot_date",
            "days_past_due",
            "arrears_amount",
            "snapshot_reason",
            "risk_band",
            "dispute_status",
            "created_at",
        }
    ),
    "collection_case": frozenset(
        {
            "case_id",
            "account_id",
            "loan_id",
            "status",
            "opened_at",
            "closed_at",
            "scored_at",
        }
    ),
    "contact_preference": frozenset(
        {
            "contact_preference_id",
            "account_id",
            "timezone",
            "allowed_start_time",
            "allowed_end_time",
            "effective_from",
            "effective_to",
            "created_at",
            "preferred_channel",
        }
    ),
    "dispute": frozenset(
        {
            "dispute_id",
            "account_id",
            "loan_id",
            "filed_at",
            "resolved_at",
            "reason_code",
            "status",
        }
    ),
    "hardship_request": frozenset(
        {
            "hardship_request_id",
            "account_id",
            "loan_id",
            "requested_at",
            "resolved_at",
            "reason_code",
            "status",
        }
    ),
    "payment": frozenset(
        {
            "payment_id",
            "account_id",
            "received_at",
            "posted_at",
            "amount",
            "unapplied_amount",
            "status",
        }
    ),
    "payment_allocation": frozenset(
        {"payment_id", "installment_id", "allocated_amount", "allocated_at"}
    ),
    "decision_log": frozenset({"decision_id", "case_id", "loan_id"}),
    "contact_attempt": frozenset(
        {"contact_attempt_id", "case_id", "attempted_at", "outcome"}
    ),
    "promise_to_pay": frozenset(
        {"promise_id", "case_id", "promised_amount", "promised_date", "status"}
    ),
    "promise_reconciliation": frozenset(
        {"promise_id", "payment_id", "reconciled_amount", "reconciled_at"}
    ),
    "state_event": frozenset(
        {
            "state_event_id",
            "entity_type",
            "case_id",
            "promise_id",
            "previous_state",
            "new_state",
            "changed_at",
            "reason_code",
        }
    ),
}

ENUMS: dict[tuple[str, str], frozenset[str]] = {
    ("customer", "customer_type"): frozenset({"individual", "organization"}),
    ("customer", "risk_band"): frozenset({"low", "medium", "high", "critical"}),
    ("account", "account_status"): frozenset({"open", "closed"}),
    ("account", "hardship_status"): frozenset(
        {"none", "requested", "approved", "declined"}
    ),
    ("loan", "product_type"): frozenset(
        {"personal", "auto", "mortgage", "credit_line"}
    ),
    ("loan", "loan_status"): frozenset({"active", "paid_off", "defaulted", "closed"}),
    ("installment", "installment_status"): frozenset(
        {"scheduled", "partially_paid", "paid", "past_due", "waived"}
    ),
    ("delinquency_snapshot", "snapshot_reason"): frozenset(
        {"month_end", "case_open", "as_of"}
    ),
    ("delinquency_snapshot", "risk_band"): frozenset(
        {"low", "medium", "high", "critical"}
    ),
    ("delinquency_snapshot", "dispute_status"): frozenset(
        {"not_disputed", "disputed", "under_review", "resolved"}
    ),
    ("contact_preference", "preferred_channel"): frozenset(
        {"phone", "email", "sms", "postal"}
    ),
    ("dispute", "reason_code"): frozenset(
        {"balance_question", "payment_not_posted", "identity_question"}
    ),
    ("dispute", "status"): frozenset({"under_review", "resolved", "withdrawn"}),
    ("hardship_request", "reason_code"): frozenset(
        {"income_loss", "medical", "disaster", "other"}
    ),
    ("hardship_request", "status"): frozenset(
        {"requested", "approved", "declined"}
    ),
    ("payment", "payment_method"): frozenset(
        {"bank_transfer", "card", "cash", "direct_debit", "other"}
    ),
    ("payment", "status"): frozenset({"posted", "pending", "reversed"}),
    ("collection_case", "status"): frozenset(
        {"open", "paused", "resolved", "closed"}
    ),
    ("collection_case", "priority_tier"): frozenset({"P1", "P2", "P3"}),
    ("decision_log", "decision_type"): frozenset(
        {"contact_allowed", "contact_blocked", "close_paid_case", "route_to_review"}
    ),
    ("decision_log", "outcome"): frozenset({"allow", "block", "close", "review"}),
    ("contact_attempt", "outcome"): frozenset(
        {
            "connected",
            "no_answer",
            "voicemail",
            "invalid_contact",
            "refused",
            "dispute_raised",
            "policy_blocked",
        }
    ),
    ("contact_attempt", "channel"): frozenset({"phone", "email", "sms", "postal"}),
    ("promise_to_pay", "status"): frozenset(
        {"PENDING", "KEPT", "PARTIAL", "BROKEN", "CANCELLED"}
    ),
    ("promise_reconciliation", "match_status"): frozenset(
        {"matched", "partial", "excess"}
    ),
    ("state_event", "entity_type"): frozenset(
        {"collection_case", "promise_to_pay"}
    ),
    ("state_event", "actor_type"): frozenset(
        {"system", "customer", "analyst", "reviewer", "administrator"}
    ),
}

DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "customer": ("created_at",),
    "account": ("opened_at", "closed_at"),
    "loan": ("origination_date", "maturity_date", "paid_off_date"),
    "installment": ("due_date", "created_at"),
    "delinquency_snapshot": ("snapshot_date", "created_at"),
    "collection_case": ("opened_at", "closed_at", "scored_at", "next_action_at"),
    "contact_preference": ("effective_from", "effective_to", "created_at"),
    "dispute": ("filed_at", "resolved_at", "created_at"),
    "hardship_request": ("requested_at", "resolved_at", "created_at"),
    "payment": ("received_at", "posted_at", "created_at"),
    "payment_allocation": ("allocated_at",),
    "decision_log": ("as_of_date", "created_at"),
    "contact_attempt": ("attempted_at", "created_at"),
    "promise_to_pay": ("promised_date", "recorded_at", "resolved_at"),
    "promise_reconciliation": ("reconciled_at",),
    "state_event": ("changed_at",),
}

FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    ("account", "customer_id", "customer", "customer_id"),
    ("loan", "account_id", "account", "account_id"),
    ("installment", "loan_id", "loan", "loan_id"),
    ("delinquency_snapshot", "loan_id", "loan", "loan_id"),
    ("collection_case", "account_id", "account", "account_id"),
    ("collection_case", "loan_id", "loan", "loan_id"),
    ("contact_preference", "account_id", "account", "account_id"),
    ("dispute", "account_id", "account", "account_id"),
    ("dispute", "loan_id", "loan", "loan_id"),
    ("hardship_request", "account_id", "account", "account_id"),
    ("hardship_request", "loan_id", "loan", "loan_id"),
    ("payment", "account_id", "account", "account_id"),
    ("payment_allocation", "payment_id", "payment", "payment_id"),
    ("payment_allocation", "installment_id", "installment", "installment_id"),
    ("decision_log", "case_id", "collection_case", "case_id"),
    ("decision_log", "loan_id", "loan", "loan_id"),
    ("contact_attempt", "case_id", "collection_case", "case_id"),
    ("promise_to_pay", "case_id", "collection_case", "case_id"),
    ("promise_reconciliation", "promise_id", "promise_to_pay", "promise_id"),
    ("promise_reconciliation", "payment_id", "payment", "payment_id"),
    ("state_event", "case_id", "collection_case", "case_id"),
    ("state_event", "promise_id", "promise_to_pay", "promise_id"),
)


@dataclass
class IntegrityReport:
    """Validation results for a dataset directory."""

    data_dir: str
    row_counts: dict[str, int] = field(default_factory=dict)
    checks_passed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def _read_tables(data_dir: Path, report: IntegrityReport) -> dict[str, list[dict[str, str]]]:
    tables: dict[str, list[dict[str, str]]] = {}
    for table in PRIMARY_KEYS:
        path = data_dir / f"{table}.csv"
        if not path.is_file():
            report.errors.append(f"missing table CSV: {path.name}")
            continue
        try:
            with path.open(encoding="utf-8-sig", newline="") as source:
                reader = csv.DictReader(source)
                headers = set(reader.fieldnames or ())
                missing_columns = REQUIRED_COLUMNS[table] - headers
                if missing_columns:
                    report.errors.append(
                        f"{path.name} is missing required columns: "
                        f"{', '.join(sorted(missing_columns))}"
                    )
                    continue
                tables[table] = list(reader)
        except (OSError, UnicodeError, csv.Error) as error:
            report.errors.append(f"cannot read {path.name}: {error}")
            continue
        report.row_counts[table] = len(tables[table])
    return tables


def _as_int(
    table: str,
    field_name: str,
    row: dict[str, str],
    row_number: int,
    report: IntegrityReport,
) -> int | None:
    try:
        return int(row[field_name])
    except (KeyError, ValueError):
        report.errors.append(
            f"{table}[{row_number}] has invalid integer {field_name}"
        )
        return None


def _as_date(
    table: str,
    field_name: str,
    value: str,
    row_number: int,
    report: IntegrityReport,
) -> date | None:
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return date.fromisoformat(value)
    except ValueError:
        report.errors.append(
            f"{table}[{row_number}] has invalid date/timestamp {field_name}"
        )
        return None


def _check_enums(tables: dict[str, list[dict[str, str]]], report: IntegrityReport) -> None:
    for (table, field_name), allowed in ENUMS.items():
        for index, row in enumerate(tables.get(table, []), start=2):
            if row.get(field_name) not in allowed:
                report.errors.append(
                    f"{table}.csv row {index}: invalid {field_name}={row.get(field_name)!r}"
                )
    report.checks_passed += 1


def _check_primary_keys(
    tables: dict[str, list[dict[str, str]]], report: IntegrityReport
) -> dict[str, set[str]]:
    primary_values: dict[str, set[str]] = {}
    for table, fields in PRIMARY_KEYS.items():
        rows = tables.get(table, [])
        seen: set[tuple[str, ...]] = set()
        values: set[str] = set()
        for index, row in enumerate(rows, start=2):
            key = tuple(row.get(field, "") for field in fields)
            if any(not value for value in key):
                report.errors.append(
                    f"{table}.csv row {index}: missing primary key field"
                )
            elif key in seen:
                report.errors.append(
                    f"{table}.csv row {index}: duplicate primary key {key!r}"
                )
            seen.add(key)
            if len(fields) == 1 and key[0]:
                values.add(key[0])
        primary_values[table] = values
    report.checks_passed += 1
    return primary_values


def _check_foreign_keys(
    tables: dict[str, list[dict[str, str]]],
    primary_values: dict[str, set[str]],
    report: IntegrityReport,
) -> None:
    for child, child_field, parent, parent_field in FOREIGN_KEYS:
        parent_ids = primary_values.get(parent, set())
        for index, row in enumerate(tables.get(child, []), start=2):
            value = row.get(child_field, "")
            nullable = child == "state_event" and child_field in {"case_id", "promise_id"}
            if nullable and not value:
                continue
            if value not in parent_ids:
                report.errors.append(
                    f"{child}.csv row {index}: {child_field} references missing "
                    f"{parent}.{parent_field}={value!r}"
                )
    loans = {row["loan_id"]: row for row in tables.get("loan", [])}
    cases = {row["case_id"]: row for row in tables.get("collection_case", [])}
    for table in ("collection_case", "dispute", "hardship_request"):
        for index, row in enumerate(tables.get(table, []), start=2):
            loan = loans.get(row["loan_id"])
            if loan and loan["account_id"] != row["account_id"]:
                report.errors.append(
                    f"{table}.csv row {index}: account does not own referenced loan"
                )
    for index, row in enumerate(tables.get("decision_log", []), start=2):
        case = cases.get(row["case_id"])
        if case and row["loan_id"] != case["loan_id"]:
            report.errors.append(
                f"decision_log.csv row {index}: loan does not match referenced case"
            )
    for index, row in enumerate(tables.get("state_event", []), start=2):
        is_case = row["entity_type"] == "collection_case"
        case_id = row.get("case_id", "")
        promise_id = row.get("promise_id", "")
        if is_case != bool(case_id) or is_case == bool(promise_id):
            report.errors.append(
                f"state_event.csv row {index}: exactly one matching target is required"
            )
    report.checks_passed += 1


def _check_dates(
    tables: dict[str, list[dict[str, str]]], report: IntegrityReport
) -> None:
    parsed: dict[tuple[str, int, str], date] = {}
    for table, fields in DATE_FIELDS.items():
        for index, row in enumerate(tables.get(table, []), start=2):
            for field_name in fields:
                value = row.get(field_name, "")
                result = _as_date(table, field_name, value, index, report)
                if result is not None:
                    parsed[(table, index, field_name)] = result

    def ordered(table: str, earlier: str, later: str, allow_equal: bool = True) -> None:
        for index, row in enumerate(tables.get(table, []), start=2):
            left = parsed.get((table, index, earlier))
            right = parsed.get((table, index, later))
            if left is not None and right is not None and (
                right < left if allow_equal else right <= left
            ):
                report.errors.append(
                    f"{table}.csv row {index}: {later} precedes {earlier}"
                )

    ordered("account", "opened_at", "closed_at")
    ordered("loan", "origination_date", "maturity_date", allow_equal=False)
    ordered("loan", "origination_date", "paid_off_date")
    ordered("contact_preference", "effective_from", "effective_to")
    ordered("dispute", "filed_at", "resolved_at")
    ordered("hardship_request", "requested_at", "resolved_at")
    ordered("payment", "received_at", "posted_at")
    ordered("promise_to_pay", "recorded_at", "promised_date")
    report.checks_passed += 1


def _check_arithmetic(
    tables: dict[str, list[dict[str, str]]], report: IntegrityReport
) -> None:
    loans = {row["loan_id"]: row for row in tables.get("loan", [])}
    installments_by_loan: dict[str, list[dict[str, str]]] = {}
    installments = {
        row["installment_id"]: row for row in tables.get("installment", [])
    }
    payments = {row["payment_id"]: row for row in tables.get("payment", [])}
    allocations_by_payment: dict[str, int] = {}
    principal_by_loan: dict[str, int] = {}
    loan_total_by_installment: dict[str, int] = {}

    for index, row in enumerate(tables.get("installment", []), start=2):
        principal = _as_int("installment", "principal_due", row, index, report)
        interest = _as_int("installment", "interest_due", row, index, report)
        total = _as_int("installment", "total_due", row, index, report)
        if None not in (principal, interest, total):
            if total != principal + interest:
                report.errors.append(
                    f"installment.csv row {index}: total_due does not equal principal plus interest"
                )
            principal_by_loan[row["loan_id"]] = (
                principal_by_loan.get(row["loan_id"], 0) + principal
            )
            installments_by_loan.setdefault(row["loan_id"], []).append(row)
            loan_total_by_installment[row["installment_id"]] = total

    for loan_id, loan in loans.items():
        principal = _as_int("loan", "principal_amount", loan, 0, report)
        if principal is not None and principal_by_loan.get(loan_id, 0) != principal:
            report.errors.append(f"loan {loan_id}: installment principal does not reconcile")

    allocation_totals_by_installment: dict[str, int] = {}
    for index, row in enumerate(tables.get("payment_allocation", []), start=2):
        amount = _as_int("payment_allocation", "allocated_amount", row, index, report)
        if amount is None:
            continue
        if amount <= 0:
            report.errors.append(f"payment_allocation.csv row {index}: amount must be positive")
        allocations_by_payment[row["payment_id"]] = (
            allocations_by_payment.get(row["payment_id"], 0) + amount
        )
        allocation_totals_by_installment[row["installment_id"]] = (
            allocation_totals_by_installment.get(row["installment_id"], 0) + amount
        )
        installment = installments.get(row["installment_id"])
        payment = payments.get(row["payment_id"])
        if installment and payment:
            loan = loans.get(installment["loan_id"])
            if loan and loan["account_id"] != payment["account_id"]:
                report.errors.append(
                    f"payment allocation {row['payment_id']}/{row['installment_id']} crosses accounts"
                )
    for payment_id, payment in payments.items():
        amount = _as_int("payment", "amount", payment, 0, report)
        unapplied = _as_int("payment", "unapplied_amount", payment, 0, report)
        if amount is not None and unapplied is not None and (
            allocations_by_payment.get(payment_id, 0) + unapplied != amount
        ):
            report.errors.append(
                f"payment {payment_id}: allocated plus unapplied does not equal payment amount"
            )
    for installment_id, total_due in loan_total_by_installment.items():
        if allocation_totals_by_installment.get(installment_id, 0) > total_due:
            report.errors.append(
                f"installment {installment_id}: allocations exceed total_due"
            )
    for index, row in enumerate(tables.get("delinquency_snapshot", []), start=2):
        for field_name in ("days_past_due", "arrears_amount"):
            value = _as_int("delinquency_snapshot", field_name, row, index, report)
            if value is not None and value < 0:
                report.errors.append(
                    f"delinquency_snapshot.csv row {index}: {field_name} cannot be negative"
                )
    report.checks_passed += 1


def _check_lifecycles(
    tables: dict[str, list[dict[str, str]]], report: IntegrityReport
) -> None:
    cases = {row["case_id"]: row for row in tables.get("collection_case", [])}
    promises = {row["promise_id"]: row for row in tables.get("promise_to_pay", [])}
    events_by_target: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in tables.get("state_event", []):
        if row.get("entity_type") == "collection_case" and row.get("case_id"):
            events_by_target.setdefault(("collection_case", row["case_id"]), []).append(row)
        elif row.get("entity_type") == "promise_to_pay" and row.get("promise_id"):
            events_by_target.setdefault(("promise_to_pay", row["promise_id"]), []).append(row)
        else:
            report.errors.append("state_event has invalid target entity references")

    for entity_type, records in (("collection_case", cases), ("promise_to_pay", promises)):
        for entity_id, record in records.items():
            rows = events_by_target.get((entity_type, entity_id), [])
            rows.sort(key=lambda row: row["changed_at"])
            previous: str | None = None
            for row in rows:
                current = row["new_state"]
                if (row.get("previous_state") or None) != previous:
                    report.errors.append(
                        f"{entity_type} {entity_id}: state-event history is discontinuous"
                    )
                if entity_type == "collection_case":
                    transitions = {
                        None: {"open", "paused", "resolved", "closed"},
                        "open": {"paused", "resolved", "closed"},
                        "paused": {"open", "resolved", "closed"},
                        "resolved": (
                            {"closed", "open"}
                            if row.get("reason_code") == "CASE_REOPENED"
                            else {"closed"}
                        ),
                        "closed": set(),
                    }
                else:
                    transitions = {
                        None: {"PENDING"},
                        "PENDING": {"KEPT", "PARTIAL", "BROKEN", "CANCELLED"},
                    }
                if current not in transitions.get(previous, set()):
                    report.errors.append(
                        f"{entity_type} {entity_id}: invalid transition {previous!r}->{current!r}"
                    )
                previous = current
            if previous != record.get("status"):
                report.errors.append(
                    f"{entity_type} {entity_id}: terminal state does not match record"
                )

    report.checks_passed += 1


def validate_dataset_directory(data_dir: Path | str) -> IntegrityReport:
    """Validate keys, references, enums, dates, arithmetic, and state lifecycles."""
    root = Path(data_dir)
    report = IntegrityReport(data_dir=str(root))
    if not root.is_dir():
        report.errors.append(f"dataset directory does not exist: {root}")
        return report
    tables = _read_tables(root, report)
    primary_values = _check_primary_keys(tables, report)
    _check_foreign_keys(tables, primary_values, report)
    _check_enums(tables, report)
    _check_dates(tables, report)
    _check_arithmetic(tables, report)
    _check_lifecycles(tables, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/full"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    report = validate_dataset_directory(args.data_dir)
    output = json.dumps(asdict(report) | {"valid": report.valid}, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
