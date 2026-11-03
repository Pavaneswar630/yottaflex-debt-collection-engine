"""Ground-truth-blind detectors for selected collection-data violations."""

import argparse
import csv
from datetime import datetime, time
import json
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo


DETECTOR_TYPES = (
    "paid_account_in_collection",
    "contact_outside_allowed_window",
    "payment_allocated_to_wrong_installment",
)
DETECTION_FIELDS = (
    "issue_type",
    "entity_type",
    "entity_id",
    "rule_id",
    "evidence",
)


def _read_csv(data_dir: Path, table: str) -> list[dict[str, str]]:
    path = data_dir / f"{table}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Required input CSV is missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _paid_collection_cases(data_dir: Path) -> list[dict[str, str]]:
    loans = {row["loan_id"]: row for row in _read_csv(data_dir, "loan")}
    detections = []
    for case in _read_csv(data_dir, "collection_case"):
        loan = loans.get(case["loan_id"])
        if loan and loan["loan_status"] == "paid_off" and case["status"] in {
            "open",
            "paused",
        }:
            detections.append(
                {
                    "issue_type": "paid_account_in_collection",
                    "entity_type": "collection_case",
                    "entity_id": case["case_id"],
                    "rule_id": "R-PAIDOFF-01",
                    "evidence": (
                        f"loan_status={loan['loan_status']}; "
                        f"case_status={case['status']}"
                    ),
                }
            )
    return detections


def _contact_window_violations(data_dir: Path) -> list[dict[str, str]]:
    preferences = {
        row["account_id"]: row for row in _read_csv(data_dir, "contact_preference")
    }
    loans = {row["loan_id"]: row for row in _read_csv(data_dir, "loan")}
    cases = {
        row["case_id"]: row for row in _read_csv(data_dir, "collection_case")
    }
    account_by_loan = {
        loan_id: loan["account_id"] for loan_id, loan in loans.items()
    }
    detections = []
    for attempt in _read_csv(data_dir, "contact_attempt"):
        case = cases.get(attempt["case_id"])
        if not case:
            continue
        account_id = account_by_loan.get(case["loan_id"])
        preference = preferences.get(account_id or "")
        if not preference:
            continue
        attempted_at = datetime.fromisoformat(
            attempt["attempted_at"].replace("Z", "+00:00")
        )
        local_at = attempted_at.astimezone(ZoneInfo(preference["timezone"]))
        local_clock = local_at.timetz().replace(tzinfo=None)
        allowed_start = max(time(8, 0), time.fromisoformat(preference["allowed_start_time"]))
        allowed_end = min(time(19, 0), time.fromisoformat(preference["allowed_end_time"]))
        effective_from = datetime.fromisoformat(preference["effective_from"]).date()
        effective_to = (
            datetime.fromisoformat(preference["effective_to"]).date()
            if preference["effective_to"]
            else None
        )
        effective = effective_from <= local_at.date() and (
            effective_to is None or local_at.date() <= effective_to
        )
        if not effective or local_clock < allowed_start or local_clock >= allowed_end:
            detections.append(
                {
                    "issue_type": "contact_outside_allowed_window",
                    "entity_type": "contact_attempt",
                    "entity_id": attempt["contact_attempt_id"],
                    "rule_id": "R-CONTACT-01",
                    "evidence": (
                        f"local_time={local_at.isoformat()}; "
                        f"permitted={allowed_start.isoformat()}-{allowed_end.isoformat()}; "
                        f"preference_effective={effective}"
                    ),
                }
            )
    return detections


def _wrong_installment_allocations(data_dir: Path) -> list[dict[str, str]]:
    installments = {
        row["installment_id"]: row for row in _read_csv(data_dir, "installment")
    }
    payments = _read_csv(data_dir, "payment")
    allocations = _read_csv(data_dir, "payment_allocation")
    by_loan: dict[str, list[dict[str, str]]] = {}
    for installment in installments.values():
        by_loan.setdefault(installment["loan_id"], []).append(installment)
    for rows in by_loan.values():
        rows.sort(key=lambda row: (row["due_date"], int(row["sequence_number"])))

    payments_by_account: dict[str, list[dict[str, str]]] = {}
    for payment in payments:
        if payment["status"] == "posted" and payment["posted_at"]:
            payments_by_account.setdefault(payment["account_id"], []).append(payment)
    for rows in payments_by_account.values():
        rows.sort(key=lambda row: (row["posted_at"], row["payment_id"]))

    allocations_by_payment: dict[str, list[dict[str, str]]] = {}
    for allocation in allocations:
        allocations_by_payment.setdefault(allocation["payment_id"], []).append(allocation)
    paid_by_installment: dict[str, int] = {}
    detections: list[dict[str, str]] = []
    detected_pairs: set[tuple[str, str]] = set()

    for payment_rows in payments_by_account.values():
        for payment in payment_rows:
            posted_date = datetime.fromisoformat(
                payment["posted_at"].replace("Z", "+00:00")
            ).date()
            candidates = [
                row
                for row in allocations_by_payment.get(payment["payment_id"], [])
                if row["installment_id"] in installments
            ]
            candidates.sort(
                key=lambda row: (
                    installments[row["installment_id"]]["due_date"],
                    int(installments[row["installment_id"]]["sequence_number"]),
                )
            )
            earlier_due = [
                installment
                for installment in by_loan.get(
                    installments[candidates[0]["installment_id"]]["loan_id"]
                    if candidates
                    else "",
                    [],
                )
                if datetime.fromisoformat(installment["due_date"]).date()
                <= posted_date
            ]
            allocated_this_payment: dict[str, int] = {}
            for allocation in candidates:
                installment_id = allocation["installment_id"]
                installment = installments[installment_id]
                amount = int(allocation["allocated_amount"])
                due_date = datetime.fromisoformat(installment["due_date"]).date()
                older_unpaid = [
                    older
                    for older in earlier_due
                    if (
                        older["due_date"],
                        int(older["sequence_number"]),
                    )
                    < (installment["due_date"], int(installment["sequence_number"]))
                    and int(older["total_due"])
                    - paid_by_installment.get(older["installment_id"], 0)
                    - allocated_this_payment.get(older["installment_id"], 0)
                    > 0
                ]
                pair = (payment["payment_id"], installment_id)
                if older_unpaid and pair not in detected_pairs:
                    evidence = (
                        f"payment_posted={posted_date.isoformat()}; "
                        f"installment_due={due_date.isoformat()}; "
                        f"older_unpaid="
                        f"{'|'.join(row['installment_id'] for row in older_unpaid)}"
                    )
                    detections.append(
                        {
                            "issue_type": "payment_allocated_to_wrong_installment",
                            "entity_type": "payment_allocation",
                            "entity_id": f"{payment['payment_id']}|{installment_id}",
                            "rule_id": "R-ALLOC-01",
                            "evidence": evidence,
                        }
                    )
                    detected_pairs.add(pair)
                allocated_this_payment[installment_id] = (
                    allocated_this_payment.get(installment_id, 0) + amount
                )
            for installment_id, amount in allocated_this_payment.items():
                paid_by_installment[installment_id] = (
                    paid_by_installment.get(installment_id, 0) + amount
                )
    return detections


def detect(data_dir: Path | str) -> list[dict[str, str]]:
    """Run configured detectors using input tables only."""
    root = Path(data_dir)
    detections = [
        *_paid_collection_cases(root),
        *_contact_window_violations(root),
        *_wrong_installment_allocations(root),
    ]
    return sorted(
        detections,
        key=lambda item: (
            item["issue_type"],
            item["entity_type"],
            item["entity_id"],
        ),
    )


def write_detections(detections: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=DETECTION_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(detections)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/full"))
    parser.add_argument("--output", type=Path, default=Path("reports/detections.csv"))
    args = parser.parse_args(argv)
    detections = detect(args.data_dir)
    write_detections(detections, args.output)
    print(json.dumps({"detections": len(detections), "by_type": {
        detector_type: sum(row["issue_type"] == detector_type for row in detections)
        for detector_type in DETECTOR_TYPES
    }}, indent=2))
    print(f"Blind detector output written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
