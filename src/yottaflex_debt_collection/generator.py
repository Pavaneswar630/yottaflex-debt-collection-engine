"""Reproducible, synthetic collection-data generation and CSV export."""

import csv
import copy
import hashlib
import json
import math
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, TypeAlias
from zoneinfo import ZoneInfo

import numpy as np
import yaml
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
RISK_SCORE_BY_BAND = {"low": 20, "medium": 45, "high": 70, "critical": 90}
SNAPSHOT_REASONS = ("month_end", "case_open", "as_of")
POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "policy.yaml"
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
    "delinquency_snapshot": (
        "snapshot_id",
        "loan_id",
        "snapshot_date",
        "snapshot_reason",
        "days_past_due",
        "arrears_amount",
        "risk_score",
        "risk_band",
        "dispute_status",
        "created_at",
    ),
    "collection_case": (
        "case_id",
        "account_id",
        "loan_id",
        "status",
        "opened_at",
        "closed_at",
        "scored_at",
        "priority_score",
        "balance_component",
        "age_component",
        "risk_component",
        "priority_tier",
        "reason_codes",
        "suppression_rule_id",
        "next_action_at",
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
    "decision_log": (
        "decision_id",
        "case_id",
        "loan_id",
        "rule_id",
        "decision_type",
        "outcome",
        "reason",
        "priority_score",
        "as_of_date",
        "created_at",
    ),
    "contact_attempt": (
        "contact_attempt_id",
        "case_id",
        "attempted_at",
        "channel",
        "outcome",
        "agent_id",
        "created_at",
    ),
    "promise_to_pay": (
        "promise_id",
        "case_id",
        "promised_amount",
        "promised_date",
        "status",
        "recorded_at",
        "resolved_at",
    ),
    "promise_reconciliation": (
        "promise_id",
        "payment_id",
        "reconciled_amount",
        "reconciled_at",
        "match_status",
    ),
    "state_event": (
        "state_event_id",
        "entity_type",
        "case_id",
        "promise_id",
        "previous_state",
        "new_state",
        "changed_at",
        "reason_code",
        "actor_type",
    ),
}


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def _month_end_dates(start: date, end: date) -> list[date]:
    dates: list[date] = []
    month = date(start.year, start.month, 1)
    while month <= end:
        month_end = date(month.year, month.month, monthrange(month.year, month.month)[1])
        if start <= month_end <= end:
            dates.append(month_end)
        month = _add_months(month, 1)
    return dates


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


def calculate_delinquency(
    installments: list[Row],
    allocations: list[Row],
    payments: list[Row],
    as_of_date: date,
) -> tuple[int, int]:
    """Return arrears cents and DPD from posted allocations due by ``as_of_date``."""
    payment_dates = {
        str(payment["payment_id"]): date.fromisoformat(str(payment["posted_at"])[:10])
        for payment in payments
        if payment["status"] == "posted" and payment["posted_at"] is not None
    }
    arrears = 0
    oldest_unpaid_due_date: date | None = None
    for installment in installments:
        due_date = date.fromisoformat(str(installment["due_date"]))
        if due_date > as_of_date:
            continue
        paid = sum(
            int(allocation["allocated_amount"])
            for allocation in allocations
            if allocation["installment_id"] == installment["installment_id"]
            and str(allocation["payment_id"]) in payment_dates
            and payment_dates[str(allocation["payment_id"])] <= as_of_date
        )
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


def _load_policy() -> dict[str, Any]:
    with POLICY_PATH.open(encoding="utf-8") as source:
        policy = yaml.safe_load(source)
    if not isinstance(policy, dict):
        raise ValueError(f"Policy must be a YAML mapping: {POLICY_PATH}")
    return policy


def _first_threshold_crossing_date(
    installments: list[Row],
    allocations: list[Row],
    payments: list[Row],
    as_of_date: date,
    threshold_days: int,
) -> date | None:
    candidates = sorted(
        {
            due_date + timedelta(days=threshold_days)
            for row in installments
            if (
                due_date := date.fromisoformat(str(row["due_date"]))
            ) + timedelta(days=threshold_days)
            <= as_of_date
        }
    )
    for candidate in candidates:
        _, days_past_due = calculate_delinquency(
            installments, allocations, payments, candidate
        )
        if days_past_due >= threshold_days:
            return candidate
    return None


def _score_case(
    arrears: int,
    principal: int,
    days_past_due: int,
    risk_score: int,
    risk_band: str,
    scoring_policy: dict[str, Any],
) -> tuple[float, float, float, float, str, str]:
    balance_component = (
        round(min(arrears / principal, 1.0), 4) if principal > 0 else 0.0
    )
    age_component: float | None = None
    age_reason = ""
    for bucket in scoring_policy["dpd_buckets"]:
        max_days = bucket["max_days"]
        if days_past_due >= bucket["min_days"] and (
            max_days is None or days_past_due <= max_days
        ):
            age_component = bucket["score"] / 100
            age_reason = (
                f"{scoring_policy['reason_codes']['age_prefix']}"
                f"{bucket['name'].upper()}"
            )
            break
    if age_component is None:
        raise ValueError(f"No DPD scoring bucket covers {days_past_due} days")

    risk_component = risk_score / 100
    balance_thresholds = scoring_policy["balance_reason_thresholds"]
    balance_reason_key = (
        "balance_high"
        if balance_component >= balance_thresholds["high_min"]
        else "balance_medium"
        if balance_component >= balance_thresholds["medium_min"]
        else "balance_low"
    )
    balance_reason = scoring_policy["reason_codes"][balance_reason_key]
    score = round(
        100
        * (
            scoring_policy["w_balance"] * balance_component
            + scoring_policy["w_age"] * age_component
            + scoring_policy["w_risk"] * risk_component
        ),
        2,
    )
    tiers = scoring_policy["tiers"]
    tier = (
        "P1"
        if score >= tiers["p1_min_score"]
        else "P2"
        if score >= tiers["p2_min_score"]
        else "P3"
    )
    reason_codes = ";".join(
        (
            scoring_policy["reason_codes"]["case_open"],
            balance_reason,
            age_reason,
            f"{scoring_policy['reason_codes']['risk_prefix']}{risk_band.upper()}",
        )
    )
    return (
        balance_component,
        age_component,
        risk_component,
        score,
        tier,
        reason_codes,
    )


def _first_matching_suppression_rule(
    loan: Row,
    account: Row,
    disputes: list[Row],
    hardship_requests: list[Row],
    contact_preference: Row,
    as_of_date: date,
    policy: dict[str, Any],
) -> str | None:
    """Return the first active suppression rule in configured precedence order."""
    rules = policy["rules"]
    for rule_id in policy["suppression"]["first_match_order"]:
        rule = rules[rule_id]
        if rule_id == "R-PAIDOFF-01":
            matches = rule["exclude_paid_off_loans"] and loan["loan_status"] == "paid_off"
        elif rule_id == "R-DISPUTE-01":
            matches = any(
                dispute["status"] in rule["statuses"]
                and date.fromisoformat(str(dispute["filed_at"])[:10]) <= as_of_date
                and (
                    dispute["resolved_at"] is None
                    or date.fromisoformat(str(dispute["resolved_at"])[:10])
                    > as_of_date
                )
                for dispute in disputes
            )
        elif rule_id == "R-HARDSHIP-01":
            matches = any(
                request["status"] in rule["statuses"]
                and date.fromisoformat(str(request["requested_at"])[:10]) <= as_of_date
                for request in hardship_requests
            ) or account["hardship_status"] in rule["statuses"]
        elif rule_id == "R-CEASE-01":
            effective_from = date.fromisoformat(str(contact_preference["effective_from"]))
            effective_to = (
                date.fromisoformat(str(contact_preference["effective_to"]))
                if contact_preference["effective_to"] is not None
                else None
            )
            matches = (
                rule["block_outbound_contact"]
                and bool(contact_preference["do_not_contact"])
                and effective_from <= as_of_date
                and (effective_to is None or effective_to >= as_of_date)
            )
        else:
            raise ValueError(f"Unsupported suppression rule in policy: {rule_id}")
        if matches:
            return rule_id
    return None


def _schedule_contact_decision(
    case: Row,
    preference: Row,
    decision_id: str,
    policy: dict[str, Any],
    scheduled_history: list[tuple[str, datetime]],
) -> tuple[Row, datetime | None]:
    """Create one auditable schedule, block, or suppression decision for a case."""
    account_id = str(case["account_id"])
    case_id = str(case["case_id"])
    loan_id = str(case["loan_id"])
    rule_id: str
    decision_type: str
    outcome: str
    reason: str
    scheduled_at: datetime | None = None

    suppression_rule_id = case["suppression_rule_id"]
    if suppression_rule_id is not None:
        rule_id = str(suppression_rule_id)
        if rule_id == "R-PAIDOFF-01":
            decision_type, outcome = "close_paid_case", "close"
        else:
            decision_type, outcome = "route_to_review", "review"
        reason = f"suppressed by first matching rule {rule_id}"
    else:
        rule = policy["rules"]["R-CONTACT-01"]
        zone = ZoneInfo(str(preference["timezone"]))
        effective_from = date.fromisoformat(str(preference["effective_from"]))
        effective_to = (
            date.fromisoformat(str(preference["effective_to"]))
            if preference["effective_to"] is not None
            else None
        )
        allowed_start = time.fromisoformat(str(preference["allowed_start_time"]))
        allowed_end = time.fromisoformat(str(preference["allowed_end_time"]))
        policy_start = time.fromisoformat(str(rule["start_local"]))
        policy_end = time.fromisoformat(str(rule["end_local"]))
        candidate_time = max(allowed_start, policy_start)
        candidate_at = datetime.combine(AS_OF_DATE, candidate_time, tzinfo=zone)
        effective = effective_from <= AS_OF_DATE and (
            effective_to is None or effective_to >= AS_OF_DATE
        )
        restricted = bool(preference["do_not_contact"]) and effective
        inside_window = (
            effective
            and candidate_time < allowed_end
            and policy_start <= candidate_time < policy_end
        )
        if restricted:
            rule_id = "R-CEASE-01"
            decision_type, outcome = "contact_blocked", "block"
            reason = "blocked by active do-not-contact restriction (R-CEASE-01)"
        elif not inside_window:
            rule_id = "R-CONTACT-01"
            decision_type, outcome = "contact_blocked", "block"
            reason = "no permissible effective local contact time (R-CONTACT-01)"
        else:
            cap_rule = policy["rules"]["R-CONTACT-02"]
            period = timedelta(days=cap_rule["period_days"])
            recent_scheduled = [
                prior_at
                for prior_account, prior_at in scheduled_history
                if prior_account == account_id
                and timedelta(0) <= candidate_at - prior_at < period
            ]
            if len(recent_scheduled) >= cap_rule["max_attempts"]:
                rule_id = "R-CONTACT-02"
                decision_type, outcome = "contact_blocked", "block"
                reason = (
                    f"weekly contact capacity reached: {len(recent_scheduled)} "
                    f"scheduled contacts in {cap_rule['period_days']} days "
                    f"(R-CONTACT-02)"
                )
            else:
                rule_id = "R-CONTACT-01"
                decision_type, outcome = "contact_allowed", "allow"
                scheduled_at = candidate_at
                scheduled_history.append((account_id, candidate_at))
                reason = (
                    f"scheduled within customer local contact window at "
                    f"{candidate_at.isoformat()} (R-CONTACT-01)"
                )

    decision = {
        "decision_id": decision_id,
        "case_id": case_id,
        "loan_id": loan_id,
        "rule_id": rule_id,
        "decision_type": decision_type,
        "outcome": outcome,
        "reason": reason,
        "priority_score": case["priority_score"],
        "as_of_date": AS_OF_DATE.isoformat(),
        "created_at": UTC_GENERATED_AT,
    }
    return decision, scheduled_at


def _suppression_rule_at(
    loan: Row,
    account: Row,
    disputes: list[Row],
    hardship_requests: list[Row],
    preference: Row,
    when: date,
    policy: dict[str, Any],
) -> str | None:
    loan_at_date = dict(loan)
    if loan["paid_off_date"] is None or date.fromisoformat(
        str(loan["paid_off_date"])
    ) > when:
        loan_at_date["loan_status"] = "active"

    active_disputes: list[Row] = []
    for dispute in disputes:
        filed_at = date.fromisoformat(str(dispute["filed_at"])[:10])
        resolved_at = (
            date.fromisoformat(str(dispute["resolved_at"])[:10])
            if dispute["resolved_at"] is not None
            else None
        )
        if (
            dispute["status"] in {"disputed", "under_review", "resolved"}
            and filed_at <= when
            and (resolved_at is None or resolved_at > when)
        ):
            active_disputes.append({**dispute, "status": "under_review"})

    active_hardships = [
        request
        for request in hardship_requests
        if request["status"] in {"requested", "approved"}
        and date.fromisoformat(str(request["requested_at"])[:10]) <= when
    ]
    account_at_date = dict(account)
    account_at_date["hardship_status"] = (
        str(active_hardships[-1]["status"]) if active_hardships else "none"
    )
    return _first_matching_suppression_rule(
        loan_at_date,
        account_at_date,
        active_disputes,
        active_hardships,
        preference,
        when,
        policy,
    )


def _make_contact_attempt(
    case: Row,
    loan: Row,
    account: Row,
    preference: Row,
    disputes: list[Row],
    hardship_requests: list[Row],
    contact_attempt_id: str,
    policy: dict[str, Any],
) -> Row:
    """Create one historical contact event using dated policy and segment rules."""
    attempt_date = date.fromisoformat(str(case["opened_at"])[:10])
    zone = ZoneInfo(str(preference["timezone"]))
    policy_rule = policy["rules"]["R-CONTACT-01"]
    start_time = max(
        time.fromisoformat(str(preference["allowed_start_time"])),
        time.fromisoformat(str(policy_rule["start_local"])),
    )
    attempted_at = datetime.combine(attempt_date, start_time, tzinfo=zone)
    effective_from = date.fromisoformat(str(preference["effective_from"]))
    effective_to = (
        date.fromisoformat(str(preference["effective_to"]))
        if preference["effective_to"] is not None
        else None
    )
    active_preference = effective_from <= attempt_date and (
        effective_to is None or effective_to >= attempt_date
    )
    active_suppression = _suppression_rule_at(
        loan,
        account,
        disputes,
        hardship_requests,
        preference,
        attempt_date,
        policy,
    )
    allowed_end = min(
        time.fromisoformat(str(preference["allowed_end_time"])),
        time.fromisoformat(str(policy_rule["end_local"])),
    )
    if (
        not active_preference
        or bool(preference["do_not_contact"])
        or active_suppression is not None
        or start_time >= allowed_end
    ):
        outcome = "policy_blocked"
    else:
        outcome_cycle = policy["rules"]["R-CONTACT-03"]["case_sequence_cycle"]
        case_sequence = int(str(case["case_id"]).rsplit("-", 1)[1])
        outcome = str(outcome_cycle[(case_sequence - 1) % len(outcome_cycle)])
    return {
        "contact_attempt_id": contact_attempt_id,
        "case_id": case["case_id"],
        "attempted_at": attempted_at.isoformat(),
        "channel": preference["preferred_channel"],
        "outcome": outcome,
        "agent_id": None,
        "created_at": UTC_GENERATED_AT,
    }


def _state_event(
    ids: IdFactory,
    entity_type: str,
    case_id: str | None,
    promise_id: str | None,
    previous_state: str | None,
    new_state: str,
    changed_at: str,
    reason_code: str,
) -> Row:
    return {
        "state_event_id": ids.next_id("state_event"),
        "entity_type": entity_type,
        "case_id": case_id,
        "promise_id": promise_id,
        "previous_state": previous_state,
        "new_state": new_state,
        "changed_at": changed_at,
        "reason_code": reason_code,
        "actor_type": "system",
    }


def _case_suppression_date(
    case: Row,
    loan: Row,
    preference: Row,
    disputes: list[Row],
    hardship_requests: list[Row],
) -> date:
    rule_id = case["suppression_rule_id"]
    if rule_id == "R-PAIDOFF-01":
        return date.fromisoformat(str(loan["paid_off_date"]))
    if rule_id == "R-DISPUTE-01":
        candidates = [
            date.fromisoformat(str(row["filed_at"])[:10])
            for row in disputes
            if row["status"] in {"disputed", "under_review"}
            and date.fromisoformat(str(row["filed_at"])[:10])
            <= AS_OF_DATE
            and (
                row["resolved_at"] is None
                or date.fromisoformat(str(row["resolved_at"])[:10]) > AS_OF_DATE
            )
        ]
    elif rule_id == "R-HARDSHIP-01":
        candidates = [
            date.fromisoformat(str(row["requested_at"])[:10])
            for row in hardship_requests
            if row["status"] in {"requested", "approved"}
            and date.fromisoformat(str(row["requested_at"])[:10]) <= AS_OF_DATE
        ]
    elif rule_id == "R-CEASE-01":
        candidates = [date.fromisoformat(str(preference["effective_from"]))]
    else:
        return date.fromisoformat(str(case["opened_at"])[:10])
    if not candidates:
        return date.fromisoformat(str(case["opened_at"])[:10])
    return min(candidates)


def _case_state_events(
    ids: IdFactory,
    cases: list[Row],
    loans_by_id: dict[str, Row],
    preferences_by_account: dict[str, Row],
    disputes_by_account: dict[str, list[Row]],
    hardships_by_account: dict[str, list[Row]],
) -> list[Row]:
    events: list[Row] = []
    for case in cases:
        case_id = str(case["case_id"])
        loan_id = str(case["loan_id"])
        account_id = str(case["account_id"])
        opened_date = date.fromisoformat(str(case["opened_at"])[:10])
        final_status = str(case["status"])
        rule_id = case["suppression_rule_id"]
        if rule_id is None:
            events.append(
                _state_event(
                    ids,
                    "collection_case",
                    case_id,
                    None,
                    None,
                    final_status,
                    str(case["opened_at"]),
                    "CASE_OPENED",
                )
            )
            continue

        suppression_date = _case_suppression_date(
            case,
            loans_by_id[loan_id],
            preferences_by_account[account_id],
            disputes_by_account.get(account_id, []),
            hardships_by_account.get(account_id, []),
        )
        if suppression_date <= opened_date:
            events.append(
                _state_event(
                    ids,
                    "collection_case",
                    case_id,
                    None,
                    None,
                    final_status,
                    str(case["opened_at"]),
                    str(rule_id),
                )
            )
        else:
            events.extend(
                (
                    _state_event(
                        ids,
                        "collection_case",
                        case_id,
                        None,
                        None,
                        "open",
                        str(case["opened_at"]),
                        "CASE_OPENED",
                    ),
                    _state_event(
                        ids,
                        "collection_case",
                        case_id,
                        None,
                        "open",
                        final_status,
                        _timestamp(suppression_date),
                        str(rule_id),
                    ),
                )
            )
    return events


def _promise_outcome(
    paid_amount: int, promised_amount: int, tolerance_pct: int
) -> str:
    if paid_amount * 100 >= promised_amount * (100 - tolerance_pct):
        return "KEPT"
    if paid_amount > 0:
        return "PARTIAL"
    return "BROKEN"


def _create_promises(
    attempts: list[Row],
    cases_by_id: dict[str, Row],
    installments_by_loan: dict[str, list[Row]],
    allocations_by_loan: dict[str, list[Row]],
    payments_by_account: dict[str, list[Row]],
    preferences_by_account: dict[str, Row],
    allocations: list[Row],
    installments_by_id: dict[str, Row],
    ids: IdFactory,
    policy: dict[str, Any],
) -> tuple[list[Row], list[Row], list[Row]]:
    promises: list[Row] = []
    reconciliations: list[Row] = []
    state_events: list[Row] = []
    allocation_amounts: dict[tuple[str, str], int] = {}
    for allocation in allocations:
        loan_id = str(
            installments_by_id[str(allocation["installment_id"])]["loan_id"]
        )
        key = (loan_id, str(allocation["payment_id"]))
        allocation_amounts[key] = allocation_amounts.get(key, 0) + int(
            allocation["allocated_amount"]
        )

    promise_policy = policy["rules"]["R-PROMISE-01"]
    reconcile_policy = policy["reconcile"]
    for attempt in attempts:
        if attempt["outcome"] != "connected":
            continue
        case = cases_by_id[str(attempt["case_id"])]
        loan_id = str(case["loan_id"])
        account_id = str(case["account_id"])
        loan_payments = payments_by_account.get(account_id, [])
        recorded_at = datetime.fromisoformat(str(attempt["attempted_at"]))
        arrears, _ = calculate_delinquency(
            installments_by_loan[loan_id],
            allocations_by_loan.get(loan_id, []),
            loan_payments,
            recorded_at.date(),
        )
        if arrears <= 0:
            continue

        amount_percent = int(promise_policy["amount_percent_of_arrears"])
        promised_amount = max(1, arrears * amount_percent // 100)
        promised_date = recorded_at.date() + timedelta(
            days=int(promise_policy["promise_due_days"])
        )
        grace_end_date = promised_date + timedelta(
            days=int(reconcile_policy["grace_days"])
        )
        grace_end = datetime.combine(
            grace_end_date,
            time.max,
            tzinfo=ZoneInfo(str(preferences_by_account[account_id]["timezone"])),
        )
        payment_candidates: list[tuple[datetime, str, int]] = []
        for payment in loan_payments:
            if payment["status"] != "posted" or payment["posted_at"] is None:
                continue
            posted_at = datetime.fromisoformat(str(payment["posted_at"]))
            allocated_amount = allocation_amounts.get(
                (loan_id, str(payment["payment_id"])), 0
            )
            if (
                allocated_amount > 0
                and posted_at > recorded_at
                and posted_at <= grace_end
                and posted_at.date() <= AS_OF_DATE
            ):
                payment_candidates.append(
                    (posted_at, str(payment["payment_id"]), allocated_amount)
                )
        payment_candidates.sort()

        promise_id = ids.next_promise_id(str(case["case_id"]))
        cumulative = 0
        kept_at: datetime | None = None
        for posted_at, payment_id, paid_amount in payment_candidates:
            cumulative += paid_amount
            if (
                cumulative * 100
                >= promised_amount * (100 - int(reconcile_policy["tolerance_pct"]))
                and kept_at is None
            ):
                kept_at = posted_at
            match_status = (
                "excess"
                if cumulative > promised_amount
                else "matched"
                if cumulative * 100
                >= promised_amount * (100 - int(reconcile_policy["tolerance_pct"]))
                else "partial"
            )
            reconciliations.append(
                {
                    "promise_id": promise_id,
                    "payment_id": payment_id,
                    "reconciled_amount": paid_amount,
                    "reconciled_at": posted_at.isoformat(),
                    "match_status": match_status,
                }
            )

        if kept_at is not None:
            status = "KEPT"
            resolved_at = kept_at.isoformat()
        elif grace_end_date <= AS_OF_DATE:
            status = _promise_outcome(
                cumulative,
                promised_amount,
                int(reconcile_policy["tolerance_pct"]),
            )
            resolved_at = grace_end.isoformat()
        else:
            status = "PENDING"
            resolved_at = None

        promise = {
            "promise_id": promise_id,
            "case_id": case["case_id"],
            "promised_amount": promised_amount,
            "promised_date": promised_date.isoformat(),
            "status": status,
            "recorded_at": recorded_at.isoformat(),
            "resolved_at": resolved_at,
        }
        promises.append(promise)
        state_events.append(
            _state_event(
                ids,
                "promise_to_pay",
                None,
                promise_id,
                None,
                "PENDING",
                recorded_at.isoformat(),
                "PROMISE_RECORDED",
            )
        )
        if status != "PENDING":
            state_events.append(
                _state_event(
                    ids,
                    "promise_to_pay",
                    None,
                    promise_id,
                    "PENDING",
                    status,
                    str(resolved_at),
                    "PROMISE_RECONCILED",
                )
            )
    return promises, reconciliations, state_events


def _row_key(table: str, row: Row) -> str:
    key_fields = {
        "payment_allocation": ("payment_id", "installment_id"),
        "promise_reconciliation": ("promise_id", "payment_id"),
    }
    if table in key_fields:
        return "|".join(str(row[field]) for field in key_fields[table])
    id_fields = {
        "customer": "customer_id",
        "account": "account_id",
        "loan": "loan_id",
        "installment": "installment_id",
        "delinquency_snapshot": "snapshot_id",
        "collection_case": "case_id",
        "decision_log": "decision_id",
        "contact_preference": "contact_preference_id",
        "dispute": "dispute_id",
        "hardship_request": "hardship_request_id",
        "payment": "payment_id",
        "contact_attempt": "contact_attempt_id",
        "promise_to_pay": "promise_id",
        "state_event": "state_event_id",
        "latent_segments": "loan_id",
    }
    return str(row[id_fields[table]])


def _dataset_snapshot(dataset: Dataset) -> dict[str, dict[str, Row]]:
    return {
        table: {_row_key(table, row): copy.deepcopy(row) for row in rows}
        for table, rows in dataset.items()
    }


def _promise_reconciliations_for(
    promise: Row,
    case: Row,
    allocations_by_loan: dict[str, list[Row]],
    payments_by_id: dict[str, Row],
    preference: Row,
    policy: dict[str, Any],
) -> tuple[list[Row], str, str | None]:
    loan_id = str(case["loan_id"])
    recorded_at = datetime.fromisoformat(str(promise["recorded_at"]))
    due_date = date.fromisoformat(str(promise["promised_date"]))
    grace_end_date = due_date + timedelta(days=int(policy["reconcile"]["grace_days"]))
    grace_end = datetime.combine(
        grace_end_date,
        time.max,
        tzinfo=ZoneInfo(str(preference["timezone"])),
    )
    amounts: dict[str, int] = {}
    posted_at_by_id: dict[str, datetime] = {}
    for allocation in allocations_by_loan.get(loan_id, []):
        payment_id = str(allocation["payment_id"])
        payment = payments_by_id[payment_id]
        if payment["status"] != "posted" or payment["posted_at"] is None:
            continue
        posted_at = datetime.fromisoformat(str(payment["posted_at"]))
        if (
            posted_at > recorded_at
            and posted_at <= grace_end
            and posted_at.date() <= AS_OF_DATE
        ):
            amounts[payment_id] = amounts.get(payment_id, 0) + int(
                allocation["allocated_amount"]
            )
            posted_at_by_id[payment_id] = posted_at

    cumulative = 0
    kept_at: datetime | None = None
    reconciliations: list[Row] = []
    promised_amount = int(promise["promised_amount"])
    tolerance_pct = int(policy["reconcile"]["tolerance_pct"])
    for payment_id in sorted(amounts, key=lambda value: (posted_at_by_id[value], value)):
        amount = amounts[payment_id]
        cumulative += amount
        threshold_reached = cumulative * 100 >= promised_amount * (100 - tolerance_pct)
        if threshold_reached and kept_at is None:
            kept_at = posted_at_by_id[payment_id]
        reconciliations.append(
            {
                "promise_id": promise["promise_id"],
                "payment_id": payment_id,
                "reconciled_amount": amount,
                "reconciled_at": posted_at_by_id[payment_id].isoformat(),
                "match_status": (
                    "excess"
                    if cumulative > promised_amount
                    else "matched"
                    if threshold_reached
                    else "partial"
                ),
            }
        )
    if kept_at is not None:
        return reconciliations, "KEPT", kept_at.isoformat()
    if grace_end_date <= AS_OF_DATE:
        status = _promise_outcome(cumulative, promised_amount, tolerance_pct)
        return reconciliations, status, grace_end.isoformat()
    return reconciliations, "PENDING", None


def _refresh_derived_records(
    dataset: Dataset,
    affected_loan_ids: set[str],
    protected_promise_ids: set[str],
    ids: IdFactory,
    policy: dict[str, Any],
) -> None:
    loans_by_id = {str(row["loan_id"]): row for row in dataset["loan"]}
    accounts_by_id = {str(row["account_id"]): row for row in dataset["account"]}
    customers_by_id = {str(row["customer_id"]): row for row in dataset["customer"]}
    cases_by_loan = {
        str(row["loan_id"]): row for row in dataset["collection_case"]
    }
    cases_by_id = {str(row["case_id"]): row for row in dataset["collection_case"]}
    installments_by_id = {
        str(row["installment_id"]): row for row in dataset["installment"]
    }
    installments_by_loan: dict[str, list[Row]] = {}
    for installment in dataset["installment"]:
        installments_by_loan.setdefault(str(installment["loan_id"]), []).append(
            installment
        )
    payments_by_id = {str(row["payment_id"]): row for row in dataset["payment"]}
    payments_by_account: dict[str, list[Row]] = {}
    for payment in dataset["payment"]:
        payments_by_account.setdefault(str(payment["account_id"]), []).append(payment)
    allocations_by_loan: dict[str, list[Row]] = {}
    paid_by_installment: dict[str, int] = {}
    for allocation in dataset["payment_allocation"]:
        installment_id = str(allocation["installment_id"])
        loan_id = str(installments_by_id[installment_id]["loan_id"])
        allocations_by_loan.setdefault(loan_id, []).append(allocation)
        paid_by_installment[installment_id] = (
            paid_by_installment.get(installment_id, 0)
            + int(allocation["allocated_amount"])
        )
    for installment in dataset["installment"]:
        installment_id = str(installment["installment_id"])
        due_date = date.fromisoformat(str(installment["due_date"]))
        paid = paid_by_installment.get(installment_id, 0)
        total_due = int(installment["total_due"])
        installment["installment_status"] = (
            "paid"
            if paid >= total_due
            else "partially_paid"
            if paid > 0
            else "past_due"
            if due_date <= AS_OF_DATE
            else "scheduled"
        )

    disputes_by_loan: dict[str, list[Row]] = {}
    for dispute in dataset["dispute"]:
        disputes_by_loan.setdefault(str(dispute["loan_id"]), []).append(dispute)
    preferences_by_account = {
        str(row["account_id"]): row for row in dataset["contact_preference"]
    }
    for snapshot in dataset["delinquency_snapshot"]:
        loan_id = str(snapshot["loan_id"])
        if loan_id not in affected_loan_ids:
            continue
        snapshot_date = date.fromisoformat(str(snapshot["snapshot_date"]))
        arrears, dpd = calculate_delinquency(
            installments_by_loan[loan_id],
            allocations_by_loan.get(loan_id, []),
            payments_by_account.get(str(loans_by_id[loan_id]["account_id"]), []),
            snapshot_date,
        )
        snapshot["arrears_amount"] = arrears
        snapshot["days_past_due"] = dpd
        snapshot["dispute_status"] = "not_disputed"
        for dispute in disputes_by_loan.get(loan_id, []):
            filed_date = date.fromisoformat(str(dispute["filed_at"])[:10])
            resolved_date = (
                date.fromisoformat(str(dispute["resolved_at"])[:10])
                if dispute["resolved_at"] is not None
                else None
            )
            if filed_date <= snapshot_date:
                if resolved_date is None or resolved_date > snapshot_date:
                    snapshot["dispute_status"] = "under_review"
                elif dispute["status"] == "resolved":
                    snapshot["dispute_status"] = "resolved"

    scoring_policy = policy["scoring"]
    for loan_id in affected_loan_ids:
        case = cases_by_loan.get(loan_id)
        if case is None:
            continue
        loan = loans_by_id[loan_id]
        account_id = str(case["account_id"])
        account = accounts_by_id[account_id]
        customer = customers_by_id[str(account["customer_id"])]
        risk_band = str(customer["risk_band"])
        arrears, dpd = calculate_delinquency(
            installments_by_loan[loan_id],
            allocations_by_loan.get(loan_id, []),
            payments_by_account.get(account_id, []),
            AS_OF_DATE,
        )
        (
            balance_component,
            age_component,
            risk_component,
            priority_score,
            priority_tier,
            reason_codes,
        ) = _score_case(
            arrears,
            int(loan["principal_amount"]),
            dpd,
            RISK_SCORE_BY_BAND[risk_band],
            risk_band,
            scoring_policy,
        )
        case.update(
            {
                "balance_component": f"{balance_component:.4f}",
                "age_component": f"{age_component:.4f}",
                "risk_component": f"{risk_component:.4f}",
                "priority_score": f"{priority_score:.2f}",
                "priority_tier": priority_tier,
                "reason_codes": reason_codes,
            }
        )
        for decision in dataset["decision_log"]:
            if decision["case_id"] == case["case_id"]:
                decision["priority_score"] = case["priority_score"]

    for promise in dataset["promise_to_pay"]:
        promise_id = str(promise["promise_id"])
        case = cases_by_id[str(promise["case_id"])]
        preference = preferences_by_account[str(case["account_id"])]
        new_rows, new_status, new_resolved_at = _promise_reconciliations_for(
            promise,
            case,
            allocations_by_loan,
            payments_by_id,
            preference,
            policy,
        )
        dataset["promise_reconciliation"] = [
            row
            for row in dataset["promise_reconciliation"]
            if row["promise_id"] != promise_id
        ]
        dataset["promise_reconciliation"].extend(new_rows)
        promise["status"] = new_status
        promise["resolved_at"] = new_resolved_at

        if promise_id in protected_promise_ids:
            continue
        events = [
            row
            for row in dataset["state_event"]
            if row["entity_type"] == "promise_to_pay"
            and row["promise_id"] == promise_id
        ]
        terminal = next(
            (row for row in events if row["new_state"] != "PENDING"), None
        )
        old_status = str(terminal["new_state"]) if terminal is not None else "PENDING"
        if old_status != new_status:
            dataset["state_event"].append(
                _state_event(
                    ids,
                    "promise_to_pay",
                    None,
                    promise_id,
                    old_status,
                    new_status,
                    new_resolved_at or _timestamp(AS_OF_DATE),
                    "PROMISE_RECONCILED",
                )
            )


def _inject_labeled_anomalies(
    dataset: Dataset,
    ids: IdFactory,
    policy: dict[str, Any],
    requested_count: int,
) -> tuple[list[Row], list[Row]]:
    before = _dataset_snapshot(dataset)
    cases_by_id = {str(row["case_id"]): row for row in dataset["collection_case"]}
    installments_by_id = {
        str(row["installment_id"]): row for row in dataset["installment"]
    }
    installments_by_loan: dict[str, list[Row]] = {}
    for installment in dataset["installment"]:
        installments_by_loan.setdefault(str(installment["loan_id"]), []).append(
            installment
        )
    payments_by_id = {str(row["payment_id"]): row for row in dataset["payment"]}
    payments_by_account: dict[str, list[Row]] = {}
    for payment in dataset["payment"]:
        payments_by_account.setdefault(str(payment["account_id"]), []).append(payment)
    allocations_by_loan: dict[str, list[Row]] = {}
    for allocation in dataset["payment_allocation"]:
        loan_id = str(installments_by_id[str(allocation["installment_id"])]["loan_id"])
        allocations_by_loan.setdefault(loan_id, []).append(allocation)
    preferences_by_account = {
        str(row["account_id"]): row for row in dataset["contact_preference"]
    }
    attempts_by_case = {
        str(row["case_id"]): row for row in dataset["contact_attempt"]
    }
    decisions_by_case = {
        str(row["case_id"]): row for row in dataset["decision_log"]
    }
    promises_by_case = {
        str(row["case_id"]): row for row in dataset["promise_to_pay"]
    }
    used_cases: set[str] = set()
    protected_promises: set[str] = set()
    affected_loans: set[str] = set()
    scenarios: list[dict[str, Any]] = []
    ground_truth: list[Row] = []
    expected_decisions: list[Row] = []

    def add_scenario(
        issue_type: str,
        case: Row,
        table: str,
        entity_id: str,
        rule_id: str,
        expected_decision: str,
        details: str,
        related_ids: list[str] | None = None,
    ) -> None:
        number = len(scenarios) + 1
        scenario_id = f"ANOM-2026-{number:06d}"
        case_id = str(case["case_id"])
        loan_id = str(case["loan_id"])
        refs = list(
            dict.fromkeys(
                [case_id, loan_id, str(case["account_id"]), *(related_ids or [])]
            )
        )
        scenario = {
            "scenario_id": scenario_id,
            "issue_type": issue_type,
            "entity_type": table,
            "entity_id": entity_id,
            "case_id": case_id,
            "loan_id": loan_id,
            "rule_id": rule_id,
            "expected_decision": expected_decision,
            "related_ids": refs,
        }
        scenarios.append(scenario)
        ground_truth.append(
            {
                "scenario_id": scenario_id,
                "issue_type": issue_type,
                "entity_type": table,
                "entity_id": entity_id,
                "is_primary": True,
                "rule_id": rule_id,
                "expected_decision": expected_decision,
                "related_ids": "|".join(refs),
                "details": details,
            }
        )
        expected_decisions.append(
            {
                "scenario_id": scenario_id,
                "issue_type": issue_type,
                "case_id": case_id,
                "loan_id": loan_id,
                "expected_decision": expected_decision,
                "rule_id": rule_id,
                "details": details,
            }
        )
        used_cases.add(case_id)
        affected_loans.add(loan_id)

    ordered_cases = sorted(dataset["collection_case"], key=lambda row: str(row["case_id"]))
    paid_cases = [
        row for row in ordered_cases
        if row["suppression_rule_id"] == "R-PAIDOFF-01"
        and not bool(
            preferences_by_account[str(row["account_id"])]["do_not_contact"]
        )
    ]
    out_window_cases = [
        row for row in ordered_cases
        if row["suppression_rule_id"] is None
        and str(row["case_id"]) in attempts_by_case
        and attempts_by_case[str(row["case_id"])]["outcome"] == "connected"
    ]
    dispute_cases = [
        row for row in ordered_cases
        if row["suppression_rule_id"] is None
        and row["status"] == "open"
    ]
    eight_am_cases = [
        row for row in ordered_cases
        if row["suppression_rule_id"] is None
        and decisions_by_case[str(row["case_id"])]["decision_type"] == "contact_allowed"
    ]
    wrong_allocation_candidates: list[tuple[Row, Row, str]] = []
    for case in ordered_cases:
        case_id = str(case["case_id"])
        loan_id = str(case["loan_id"])
        if case["suppression_rule_id"] is not None or case_id in promises_by_case:
            continue
        rows_by_sequence = {
            int(row["sequence_number"]): row
            for row in installments_by_loan[loan_id]
        }
        earlier = rows_by_sequence.get(2)
        later = rows_by_sequence.get(3)
        if earlier is None or later is None:
            continue
        case_open_date = date.fromisoformat(str(case["opened_at"])[:10])
        target_id = str(later["installment_id"])
        existing_pairs = {
            (str(row["payment_id"]), str(row["installment_id"]))
            for row in allocations_by_loan.get(loan_id, [])
        }
        for allocation in allocations_by_loan.get(loan_id, []):
            if allocation["installment_id"] != earlier["installment_id"]:
                continue
            amount = int(allocation["allocated_amount"])
            if amount > int(later["total_due"]):
                continue
            payment_id = str(allocation["payment_id"])
            if (payment_id, target_id) in existing_pairs:
                continue
            previous_installment_id = str(allocation["installment_id"])
            allocation["installment_id"] = target_id
            crossing_date = _first_threshold_crossing_date(
                installments_by_loan[loan_id],
                allocations_by_loan.get(loan_id, []),
                payments_by_account.get(str(case["account_id"]), []),
                AS_OF_DATE,
                int(policy["rules"]["R-CASE-01"]["dpd_threshold"]),
            )
            allocation["installment_id"] = previous_installment_id
            if crossing_date == case_open_date:
                wrong_allocation_candidates.append((case, allocation, target_id))
                break

    promise_candidates: list[tuple[Row, int]] = []
    for case_id, promise in promises_by_case.items():
        case = cases_by_id[case_id]
        recorded_date = datetime.fromisoformat(str(promise["recorded_at"])).date()
        arrears, _ = calculate_delinquency(
            installments_by_loan[str(case["loan_id"])],
            allocations_by_loan.get(str(case["loan_id"]), []),
            payments_by_account.get(str(case["account_id"]), []),
            recorded_date,
        )
        if arrears <= 0:
            continue
        preference = preferences_by_account[str(case["account_id"])]
        candidate_statuses = []
        for candidate_amount in (arrears, arrears + 1):
            candidate = {**promise, "promised_amount": candidate_amount}
            _, candidate_status, _ = _promise_reconciliations_for(
                candidate,
                case,
                allocations_by_loan,
                payments_by_id,
                preference,
                policy,
            )
            candidate_statuses.append(candidate_status)
        if candidate_statuses == [promise["status"], promise["status"]]:
            promise_candidates.append((case, arrears))

    if requested_count > 0 and ordered_cases:
        count = min(
            requested_count,
            len(ordered_cases) // 7,
            len(paid_cases),
            len(out_window_cases) // 2,
            len(wrong_allocation_candidates),
            len(promise_candidates) // 2,
            len(dispute_cases),
            len(eight_am_cases) // 2,
        )

        def available(rows: list[Row]) -> list[Row]:
            return [row for row in rows if str(row["case_id"]) not in used_cases]

        for case in available(paid_cases)[:count]:
            loan_id = str(case["loan_id"])
            account_id = str(case["account_id"])
            case["status"] = "open"
            case["closed_at"] = None
            case["suppression_rule_id"] = None
            preference = preferences_by_account[account_id]
            local_at = datetime.combine(
                AS_OF_DATE,
                max(
                    time.fromisoformat(str(preference["allowed_start_time"])),
                    time.fromisoformat(str(policy["rules"]["R-CONTACT-01"]["start_local"])),
                ),
                tzinfo=ZoneInfo(str(preference["timezone"])),
            )
            case["next_action_at"] = local_at.isoformat()
            decision = decisions_by_case[str(case["case_id"])]
            decision.update(
                {
                    "rule_id": "R-CONTACT-01",
                    "decision_type": "contact_allowed",
                    "outcome": "allow",
                    "reason": (
                        f"scheduled within customer local contact window at "
                        f"{local_at.isoformat()} (R-CONTACT-01)"
                    ),
                }
            )
            dataset["state_event"].append(
                _state_event(
                    ids,
                    "collection_case",
                    str(case["case_id"]),
                    None,
                    "resolved",
                    "open",
                    _timestamp(AS_OF_DATE),
                    "CASE_REOPENED",
                )
            )
            add_scenario(
                "paid_account_in_collection",
                case,
                "collection_case",
                str(case["case_id"]),
                "R-PAIDOFF-01",
                "close_paid_case",
                "Paid-off loan remains open and is scheduled for contact.",
                [str(decision["decision_id"])],
            )

        for case in available(out_window_cases)[:count]:
            case_id = str(case["case_id"])
            preference = preferences_by_account[str(case["account_id"])]
            attempted_at = datetime.combine(
                AS_OF_DATE,
                time(7, 59),
                tzinfo=ZoneInfo(str(preference["timezone"])),
            )
            attempt = attempts_by_case[case_id]
            attempt["attempted_at"] = attempted_at.isoformat()
            attempt["outcome"] = "connected"
            case["next_action_at"] = None
            decision = decisions_by_case[case_id]
            decision.update(
                {
                    "rule_id": "R-CONTACT-01",
                    "decision_type": "contact_blocked",
                    "outcome": "block",
                    "reason": "no permissible effective local contact time (R-CONTACT-01)",
                }
            )
            add_scenario(
                "contact_outside_allowed_window",
                case,
                "contact_attempt",
                str(attempt["contact_attempt_id"]),
                "R-CONTACT-01",
                "block_contact",
                "Synthetic contact attempt at 07:59 customer-local time.",
                [str(decision["decision_id"]), str(attempt["contact_attempt_id"])],
            )

        for case, allocation, target_id in wrong_allocation_candidates:
            if str(case["case_id"]) in used_cases:
                continue
            old_id = str(allocation["installment_id"])
            payment_id = str(allocation["payment_id"])
            allocation["installment_id"] = target_id
            add_scenario(
                "payment_allocated_to_wrong_installment",
                case,
                "payment_allocation",
                f"{payment_id}|{old_id}->{target_id}",
                "R-ALLOC-01",
                "reallocate_oldest_due_first",
                "Allocation was moved from installment 2 to installment 3.",
                [payment_id, old_id, target_id],
            )
            if len([item for item in scenarios if item["issue_type"] == "payment_allocated_to_wrong_installment"]) >= count:
                break

        for case, arrears in promise_candidates:
            if str(case["case_id"]) in used_cases:
                continue
            promise = promises_by_case[str(case["case_id"])]
            promise["promised_amount"] = arrears + 1
            protected_promises.add(str(promise["promise_id"]))
            add_scenario(
                "promise_exceeds_arrears",
                case,
                "promise_to_pay",
                str(promise["promise_id"]),
                "R-PROMISE-01",
                "reject_oversized_promise",
                f"Promise is {arrears + 1} cents while arrears are {arrears} cents.",
                [str(promise["promise_id"])],
            )
            if len([item for item in scenarios if item["issue_type"] == "promise_exceeds_arrears"]) >= count:
                break

        for case in available(dispute_cases)[:count]:
            case_id = str(case["case_id"])
            loan_id = str(case["loan_id"])
            account_id = str(case["account_id"])
            dispute_id = ids.next_id("dispute")
            filed_at = _timestamp(AS_OF_DATE - timedelta(days=1))
            dataset["dispute"].append(
                {
                    "dispute_id": dispute_id,
                    "account_id": account_id,
                    "loan_id": loan_id,
                    "filed_at": filed_at,
                    "reason_code": "balance_question",
                    "status": "under_review",
                    "resolved_at": None,
                    "created_at": UTC_GENERATED_AT,
                }
            )
            add_scenario(
                "disputed_debt_treated_as_confirmed",
                case,
                "dispute",
                dispute_id,
                "R-DISPUTE-01",
                "suppress_and_route_to_review",
                "An active dispute exists while the collection case remains open.",
                [dispute_id, account_id],
            )

        for case in available(eight_am_cases)[:count]:
            case_id = str(case["case_id"])
            preference = preferences_by_account[str(case["account_id"])]
            preference["allowed_start_time"] = "08:00:00"
            local_at = datetime.combine(
                AS_OF_DATE,
                time(8, 0),
                tzinfo=ZoneInfo(str(preference["timezone"])),
            )
            attempt = attempts_by_case[case_id]
            attempt["attempted_at"] = local_at.isoformat()
            attempt["outcome"] = "connected"
            case["next_action_at"] = local_at.isoformat()
            decision = decisions_by_case[case_id]
            decision.update(
                {
                    "rule_id": "R-CONTACT-01",
                    "decision_type": "contact_allowed",
                    "outcome": "allow",
                    "reason": (
                        f"scheduled within customer local contact window at "
                        f"{local_at.isoformat()} (R-CONTACT-01)"
                    ),
                }
            )
            add_scenario(
                "near_miss_contact_at_0800",
                case,
                "contact_attempt",
                str(attempt["contact_attempt_id"]),
                "R-CONTACT-01",
                "allow_contact",
                "Valid boundary contact at exactly 08:00 customer-local time.",
                [
                    str(preference["contact_preference_id"]),
                    str(decision["decision_id"]),
                ],
            )

        for case, arrears in promise_candidates:
            if str(case["case_id"]) in used_cases:
                continue
            promise = promises_by_case[str(case["case_id"])]
            promise["promised_amount"] = arrears
            protected_promises.add(str(promise["promise_id"]))
            add_scenario(
                "near_miss_promise_equals_arrears",
                case,
                "promise_to_pay",
                str(promise["promise_id"]),
                "R-PROMISE-01",
                "allow_full_arrears_promise",
                f"Promise equals arrears exactly at {arrears} cents.",
                [str(promise["promise_id"])],
            )
            if len([item for item in scenarios if item["issue_type"] == "near_miss_promise_equals_arrears"]) >= count:
                break

    _refresh_derived_records(
        dataset,
        affected_loans,
        protected_promises,
        ids,
        policy,
    )

    label_fields = (
        "scenario_id",
        "issue_type",
        "entity_type",
        "entity_id",
        "is_primary",
        "rule_id",
        "expected_decision",
        "related_ids",
        "details",
    )
    labelled_changes: set[tuple[str, str]] = set()
    scenario_ids_by_reference: dict[str, set[str]] = {}
    for scenario in scenarios:
        scenario_id = str(scenario["scenario_id"])
        for reference in scenario["related_ids"]:
            scenario_ids_by_reference.setdefault(reference, set()).add(scenario_id)
        table = str(scenario["entity_type"])
        entity_id = str(scenario["entity_id"])
        if table == "payment_allocation":
            payment_id, old_target = entity_id.split("|", 1)
            old_id, new_id = old_target.split("->", 1)
            labelled_changes.add((table, f"{payment_id}|{old_id}"))
            labelled_changes.add((table, f"{payment_id}|{new_id}"))
        else:
            labelled_changes.add((table, entity_id))

    after = _dataset_snapshot(dataset)
    for table in sorted(set(before) | set(after)):
        prior_rows = before.get(table, {})
        current_rows = after.get(table, {})
        for row_id in sorted(set(prior_rows) | set(current_rows)):
            if prior_rows.get(row_id) == current_rows.get(row_id):
                continue
            if (table, row_id) in labelled_changes:
                continue
            row = current_rows.get(row_id) or prior_rows[row_id]
            references = {
                str(value) for value in row.values() if isinstance(value, str)
            }
            related_scenarios = sorted(
                {
                    scenario_id
                    for reference in references
                    for scenario_id in scenario_ids_by_reference.get(reference, ())
                }
            )
            if not related_scenarios:
                raise ValueError(f"Unlabelled injected change in {table} row {row_id}")
            ground_truth.append(
                {
                    "scenario_id": related_scenarios[0],
                    "issue_type": "derived_recalculation",
                    "entity_type": table,
                    "entity_id": row_id,
                    "is_primary": False,
                    "rule_id": "DERIVED-RECOMPUTE",
                    "expected_decision": "recomputed_from_source",
                    "related_ids": "|".join(related_scenarios),
                    "details": "Derived row refreshed after the labeled source mutation.",
                }
            )
            labelled_changes.add((table, row_id))
    changed_rows = {
        (table, row_id)
        for table in set(before) | set(after)
        for row_id in set(before.get(table, {})) | set(after.get(table, {}))
        if before.get(table, {}).get(row_id) != after.get(table, {}).get(row_id)
    }
    if changed_rows != labelled_changes.intersection(changed_rows):
        raise ValueError("Anomaly injection changed rows without ground-truth labels")

    return ground_truth, expected_decisions


def generate_dataset(
    loans: int = 10_000,
    seed: int = DEFAULT_SEED,
    output_dir: Path | str | None = None,
    inject_anomalies: bool = False,
    anomaly_rows_per_type: int = 50,
    dataset_name: str | None = None,
) -> Dataset:
    """Generate synthetic records, optionally writing CSVs under ``output_dir``.

    Input exports are written below ``data/<dataset_name>/`` and isolated labels
    below ``ground_truth/<dataset_name>/``. Optional anomaly injection is
    performed only after the clean baseline passes validation. No customer PII
    or external data is used.
    """
    if isinstance(loans, bool) or not isinstance(loans, int) or loans < 1:
        raise ValueError("loans must be a positive integer")
    if (
        isinstance(anomaly_rows_per_type, bool)
        or not isinstance(anomaly_rows_per_type, int)
        or anomaly_rows_per_type < 0
    ):
        raise ValueError("anomaly_rows_per_type must be a non-negative integer")
    if dataset_name is None:
        dataset_name = "starter" if loans <= 100 else "full"
    if dataset_name not in {"full", "starter"}:
        raise ValueError("dataset_name must be 'full' or 'starter'")
    policy = _load_policy()
    threshold_days = policy["rules"]["R-CASE-01"]["dpd_threshold"]
    scoring_policy = policy["scoring"]
    suppression_order = policy["suppression"]["first_match_order"]
    expected_suppression_rules = {
        "R-PAIDOFF-01",
        "R-DISPUTE-01",
        "R-HARDSHIP-01",
        "R-CEASE-01",
    }
    if (
        len(suppression_order) != len(set(suppression_order))
        or set(suppression_order) != expected_suppression_rules
    ):
        raise ValueError("Suppression order must contain each supported rule exactly once")
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

    customers_by_id = {str(row["customer_id"]): row for row in customers}
    accounts_by_id = {str(row["account_id"]): row for row in accounts}
    disputes_by_loan: dict[str, list[Row]] = {}
    disputes_by_account: dict[str, list[Row]] = {}
    for dispute in disputes:
        disputes_by_loan.setdefault(str(dispute["loan_id"]), []).append(dispute)
        disputes_by_account.setdefault(str(dispute["account_id"]), []).append(dispute)
    hardship_by_account: dict[str, list[Row]] = {}
    for request in hardship_requests:
        hardship_by_account.setdefault(str(request["account_id"]), []).append(request)
    preferences_by_account = {
        str(preference["account_id"]): preference
        for preference in contact_preferences
    }
    payments_by_account: dict[str, list[Row]] = {}
    for payment in payments:
        payments_by_account.setdefault(str(payment["account_id"]), []).append(payment)
    loan_by_installment = {
        str(installment["installment_id"]): str(installment["loan_id"])
        for installment in installments
    }
    allocations_by_loan: dict[str, list[Row]] = {}
    for allocation in allocations:
        loan_id = loan_by_installment[str(allocation["installment_id"])]
        allocations_by_loan.setdefault(loan_id, []).append(allocation)

    delinquency_snapshots: list[Row] = []
    collection_cases: list[Row] = []
    for loan in loans_rows:
        loan_id = str(loan["loan_id"])
        account_id = str(loan["account_id"])
        loan_installments = installments_by_loan[loan_id]
        loan_payments = payments_by_account.get(account_id, [])
        loan_allocations = allocations_by_loan.get(loan_id, [])
        snapshot_reasons: dict[date, set[str]] = {}
        for month_end in _month_end_dates(
            date.fromisoformat(str(loan["origination_date"])), AS_OF_DATE
        ):
            snapshot_reasons.setdefault(month_end, set()).add("month_end")
        case_open_date = _first_threshold_crossing_date(
            loan_installments,
            loan_allocations,
            loan_payments,
            AS_OF_DATE,
            threshold_days,
        )
        if case_open_date is not None:
            snapshot_reasons.setdefault(case_open_date, set()).add("case_open")
            suppression_rule_id = _first_matching_suppression_rule(
                loan,
                accounts_by_id[account_id],
                disputes_by_account.get(account_id, []),
                hardship_by_account.get(account_id, []),
                preferences_by_account[account_id],
                AS_OF_DATE,
                policy,
            )
            arrears_at_score, dpd_at_score = calculate_delinquency(
                loan_installments,
                loan_allocations,
                loan_payments,
                AS_OF_DATE,
            )
            customer_id = account_customer[account_id]
            risk_band = str(customers_by_id[customer_id]["risk_band"])
            risk_score = RISK_SCORE_BY_BAND[risk_band]
            (
                balance_component,
                age_component,
                risk_component,
                priority_score,
                priority_tier,
                reason_codes,
            ) = _score_case(
                arrears_at_score,
                int(loan["principal_amount"]),
                dpd_at_score,
                risk_score,
                risk_band,
                scoring_policy,
            )
            is_paid_off = suppression_rule_id == "R-PAIDOFF-01"
            paid_off_date = loan["paid_off_date"]
            status = (
                "resolved"
                if is_paid_off
                else policy["suppression"]["disposition"].get(
                    suppression_rule_id, "open"
                )
            )
            collection_cases.append(
                {
                    "case_id": ids.next_id("collection_case"),
                    "account_id": account_id,
                    "loan_id": loan_id,
                    "status": status,
                    "opened_at": _timestamp(case_open_date),
                    "closed_at": (
                        _timestamp(date.fromisoformat(str(paid_off_date)))
                        if is_paid_off
                        else None
                    ),
                    "scored_at": AS_OF_DATE.isoformat(),
                    "priority_score": f"{priority_score:.2f}",
                    "balance_component": f"{balance_component:.4f}",
                    "age_component": f"{age_component:.4f}",
                    "risk_component": f"{risk_component:.4f}",
                    "priority_tier": priority_tier,
                    "reason_codes": reason_codes,
                    "suppression_rule_id": suppression_rule_id,
                    "next_action_at": None,
                }
            )
        snapshot_reasons.setdefault(AS_OF_DATE, set()).add("as_of")
        customer_id = account_customer[account_id]
        customer_risk_band = str(customers_by_id[customer_id]["risk_band"])
        risk_score = RISK_SCORE_BY_BAND[customer_risk_band]
        for snapshot_date in sorted(snapshot_reasons):
            arrears_amount, days_past_due = calculate_delinquency(
                loan_installments,
                loan_allocations,
                loan_payments,
                snapshot_date,
            )
            dispute_status = "not_disputed"
            for dispute in disputes_by_loan.get(loan_id, []):
                filed_date = date.fromisoformat(str(dispute["filed_at"])[:10])
                if filed_date > snapshot_date:
                    continue
                resolved_date = (
                    date.fromisoformat(str(dispute["resolved_at"])[:10])
                    if dispute["resolved_at"] is not None
                    else None
                )
                if resolved_date is None or resolved_date > snapshot_date:
                    dispute_status = "under_review"
                elif dispute["status"] == "resolved":
                    dispute_status = "resolved"
                else:
                    dispute_status = "not_disputed"
            for reason in SNAPSHOT_REASONS:
                if reason not in snapshot_reasons[snapshot_date]:
                    continue
                delinquency_snapshots.append(
                    {
                        "snapshot_id": ids.next_id("delinquency_snapshot"),
                        "loan_id": loan_id,
                        "snapshot_date": snapshot_date.isoformat(),
                        "snapshot_reason": reason,
                        "days_past_due": days_past_due,
                        "arrears_amount": arrears_amount,
                        "risk_score": risk_score,
                        "risk_band": customer_risk_band,
                        "dispute_status": dispute_status,
                        "created_at": UTC_GENERATED_AT,
                    }
                )

    cases_by_id = {str(row["case_id"]): row for row in collection_cases}
    generated_loans_by_id = {str(row["loan_id"]): row for row in loans_rows}
    contact_attempts = [
        _make_contact_attempt(
            case,
            generated_loans_by_id[str(case["loan_id"])],
            accounts_by_id[str(case["account_id"])],
            preferences_by_account[str(case["account_id"])],
            disputes_by_account.get(str(case["account_id"]), []),
            hardship_by_account.get(str(case["account_id"]), []),
            ids.next_contact_attempt_id(str(case["case_id"])),
            policy,
        )
        for case in collection_cases
    ]
    scheduled_history = [
        (
            str(cases_by_id[str(attempt["case_id"])]["account_id"]),
            datetime.fromisoformat(str(attempt["attempted_at"])),
        )
        for attempt in contact_attempts
        if attempt["outcome"] != "policy_blocked"
    ]
    decision_logs: list[Row] = []
    for case in sorted(
        collection_cases,
        key=lambda row: (-float(row["priority_score"]), str(row["case_id"])),
    ):
        account_id = str(case["account_id"])
        decision, scheduled_at = _schedule_contact_decision(
            case,
            preferences_by_account[account_id],
            ids.next_id("decision_log"),
            policy,
            scheduled_history,
        )
        decision_logs.append(decision)
        case["next_action_at"] = (
            scheduled_at.isoformat() if scheduled_at is not None else None
        )

    promises, promise_reconciliations, promise_state_events = _create_promises(
        contact_attempts,
        cases_by_id,
        installments_by_loan,
        allocations_by_loan,
        payments_by_account,
        preferences_by_account,
        allocations,
        {str(row["installment_id"]): row for row in installments},
        ids,
        policy,
    )
    state_events = _case_state_events(
        ids,
        collection_cases,
        generated_loans_by_id,
        preferences_by_account,
        disputes_by_account,
        hardship_by_account,
    )
    state_events.extend(promise_state_events)

    dataset: Dataset = {
        "customer": customers,
        "account": accounts,
        "loan": loans_rows,
        "installment": installments,
        "delinquency_snapshot": delinquency_snapshots,
        "collection_case": collection_cases,
        "decision_log": decision_logs,
        "contact_preference": contact_preferences,
        "dispute": disputes,
        "hardship_request": hardship_requests,
        "payment": payments,
        "payment_allocation": allocations,
        "contact_attempt": contact_attempts,
        "promise_to_pay": promises,
        "promise_reconciliation": promise_reconciliations,
        "state_event": state_events,
        "latent_segments": [
            {"loan_id": loan_id, "segment": segment_by_loan[loan_id]}
            for loan_id in (str(row["loan_id"]) for row in loans_rows)
        ],
    }
    validate_dataset(dataset)
    ground_truth: list[Row] = []
    expected_decisions: list[Row] = []
    if inject_anomalies:
        ground_truth, expected_decisions = _inject_labeled_anomalies(
            dataset, ids, policy, anomaly_rows_per_type
        )
    if output_dir is not None:
        write_dataset(
            dataset,
            Path(output_dir),
            ground_truth,
            expected_decisions,
            seed=seed,
            dataset_name=dataset_name,
        )
    return dataset


def validate_dataset(dataset: Dataset) -> None:
    """Validate generated identifiers, joins, schedules, and payment reconciliation."""
    id_fields = {
        "customer": "customer_id",
        "account": "account_id",
        "loan": "loan_id",
        "installment": "installment_id",
        "delinquency_snapshot": "snapshot_id",
        "collection_case": "case_id",
        "contact_preference": "contact_preference_id",
        "dispute": "dispute_id",
        "hardship_request": "hardship_request_id",
        "payment": "payment_id",
        "decision_log": "decision_id",
        "contact_attempt": "contact_attempt_id",
        "promise_to_pay": "promise_id",
        "state_event": "state_event_id",
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
    cases_by_loan: set[str] = set()
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
    payments_by_id = {
        str(row["payment_id"]): row for row in dataset["payment"]
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
    payments_by_account: dict[str, list[Row]] = {}
    for payment in dataset["payment"]:
        payments_by_account.setdefault(str(payment["account_id"]), []).append(payment)
    preferences_by_account = {
        str(row["account_id"]): row for row in dataset["contact_preference"]
    }
    disputes_by_account: dict[str, list[Row]] = {}
    for dispute in dataset["dispute"]:
        disputes_by_account.setdefault(str(dispute["account_id"]), []).append(dispute)
    hardships_by_account: dict[str, list[Row]] = {}
    for request in dataset["hardship_request"]:
        hardships_by_account.setdefault(str(request["account_id"]), []).append(request)
    allocations_by_loan: dict[str, list[Row]] = {}
    for allocation in dataset["payment_allocation"]:
        loan_id = str(
            installments_by_id[str(allocation["installment_id"])]["loan_id"]
        )
        allocations_by_loan.setdefault(loan_id, []).append(allocation)
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
    snapshot_keys: set[tuple[str, str, str]] = set()
    for snapshot in dataset["delinquency_snapshot"]:
        loan_id = str(snapshot["loan_id"])
        snapshot_date = date.fromisoformat(str(snapshot["snapshot_date"]))
        reason = str(snapshot["snapshot_reason"])
        if loan_id not in loan_ids:
            raise ValueError("delinquency snapshot references an unknown loan")
        if snapshot_date > AS_OF_DATE or reason not in SNAPSHOT_REASONS:
            raise ValueError("delinquency snapshot has an invalid date or reason")
        key = (loan_id, str(snapshot["snapshot_date"]), reason)
        if key in snapshot_keys:
            raise ValueError("duplicate delinquency snapshot trigger")
        snapshot_keys.add(key)
        arrears, dpd = calculate_delinquency(
            grouped_installments[loan_id],
            allocations_by_loan.get(loan_id, []),
            payments_by_account.get(
                str(loans_by_id[loan_id]["account_id"]), []
            ),
            snapshot_date,
        )
        if int(snapshot["arrears_amount"]) != arrears:
            raise ValueError("snapshot arrears do not reconcile to source records")
        if int(snapshot["days_past_due"]) != dpd:
            raise ValueError("snapshot days-past-due do not reconcile to source records")
        if snapshot["risk_band"] not in RISK_SCORE_BY_BAND:
            raise ValueError("snapshot has an invalid risk band")
        if int(snapshot["risk_score"]) != RISK_SCORE_BY_BAND[str(snapshot["risk_band"])]:
            raise ValueError("snapshot risk score does not match its risk band")
    policy = _load_policy()
    threshold_days = policy["rules"]["R-CASE-01"]["dpd_threshold"]
    scoring_policy = policy["scoring"]
    for case in dataset["collection_case"]:
        loan_id = str(case["loan_id"])
        if loan_id not in loans_by_id or str(case["account_id"]) != str(
            loans_by_id[loan_id]["account_id"]
        ):
            raise ValueError("collection case references an invalid loan/account")
        if loan_id in cases_by_loan:
            raise ValueError("a loan has more than one threshold-triggered case")
        cases_by_loan.add(loan_id)
        opened_at = date.fromisoformat(str(case["opened_at"])[:10])
        expected_opened_at = _first_threshold_crossing_date(
            grouped_installments[loan_id],
            allocations_by_loan.get(loan_id, []),
            payments_by_account.get(str(case["account_id"]), []),
            AS_OF_DATE,
            threshold_days,
        )
        if expected_opened_at != opened_at:
            raise ValueError("collection case was not opened on its first threshold date")
        if case["scored_at"] != AS_OF_DATE.isoformat():
            raise ValueError("collection case score must use the fixed as-of date")
        arrears, dpd = calculate_delinquency(
            grouped_installments[loan_id],
            allocations_by_loan.get(loan_id, []),
            payments_by_account.get(str(case["account_id"]), []),
            AS_OF_DATE,
        )
        customer_id = str(accounts_by_id[str(case["account_id"])]["customer_id"])
        risk_band = str(customers_by_id[customer_id]["risk_band"])
        (
            balance_component,
            age_component,
            risk_component,
            expected_score,
            expected_tier,
            expected_reasons,
        ) = _score_case(
            arrears,
            int(loans_by_id[loan_id]["principal_amount"]),
            dpd,
            RISK_SCORE_BY_BAND[risk_band],
            risk_band,
            scoring_policy,
        )
        expected_components = (balance_component, age_component, risk_component)
        actual_components = (
            float(case["balance_component"]),
            float(case["age_component"]),
            float(case["risk_component"]),
        )
        if actual_components != expected_components:
            raise ValueError("collection case components do not match as-of records")
        if float(case["priority_score"]) != expected_score:
            raise ValueError("collection case priority score does not match components")
        if case["priority_tier"] != expected_tier:
            raise ValueError("collection case tier does not match its priority score")
        if case["reason_codes"] != expected_reasons:
            raise ValueError("collection case reason codes do not match score inputs")
        account_id = str(case["account_id"])
        expected_suppression = _first_matching_suppression_rule(
            loans_by_id[loan_id],
            accounts_by_id[account_id],
            disputes_by_account.get(account_id, []),
            hardships_by_account.get(account_id, []),
            preferences_by_account[account_id],
            AS_OF_DATE,
            policy,
        )
        if case["suppression_rule_id"] != expected_suppression:
            raise ValueError("collection case did not retain the first matching suppression rule")
        expected_status = (
            "resolved"
            if expected_suppression == "R-PAIDOFF-01"
            else policy["suppression"]["disposition"].get(
                expected_suppression, "open"
            )
        )
        if case["status"] != expected_status:
            raise ValueError("collection case status does not match suppression policy")
    cases_by_id = {
        str(row["case_id"]): row for row in dataset["collection_case"]
    }
    decisions_by_case: dict[str, list[Row]] = {}
    for decision in dataset["decision_log"]:
        case_id = str(decision["case_id"])
        if case_id not in cases_by_id:
            raise ValueError("decision log references an unknown case")
        if decision["loan_id"] != cases_by_id[case_id]["loan_id"]:
            raise ValueError("decision log loan does not match its collection case")
        if decision["rule_id"] not in policy["rules"]:
            raise ValueError("decision log references an unknown policy rule")
        if decision["as_of_date"] != AS_OF_DATE.isoformat():
            raise ValueError("decision log must use the fixed as-of date")
        decisions_by_case.setdefault(case_id, []).append(decision)
    if set(decisions_by_case) != set(cases_by_id) or any(
        len(rows) != 1 for rows in decisions_by_case.values()
    ):
        raise ValueError("each collection case must have exactly one scheduling decision")
    for case_id, case in cases_by_id.items():
        decision = decisions_by_case[case_id][0]
        scheduled = decision["decision_type"] == "contact_allowed"
        suppression_rule = case["suppression_rule_id"]
        if suppression_rule is not None:
            expected_type, expected_outcome = (
                ("close_paid_case", "close")
                if suppression_rule == "R-PAIDOFF-01"
                else ("route_to_review", "review")
            )
            if (
                decision["rule_id"] != suppression_rule
                or decision["decision_type"] != expected_type
                or decision["outcome"] != expected_outcome
            ):
                raise ValueError("suppressed contact decision does not match first rule")
        if scheduled:
            if (
                decision["outcome"] != "allow"
                or decision["rule_id"] != "R-CONTACT-01"
                or case["next_action_at"] is None
            ):
                raise ValueError("scheduled contact decision is inconsistent")
            scheduled_at = datetime.fromisoformat(str(case["next_action_at"]))
            preference = preferences_by_account[str(case["account_id"])]
            local_at = scheduled_at.astimezone(
                ZoneInfo(str(preference["timezone"]))
            )
            contact_rule = policy["rules"]["R-CONTACT-01"]
            if not (
                time.fromisoformat(str(contact_rule["start_local"]))
                <= local_at.timetz().replace(tzinfo=None)
                < time.fromisoformat(str(contact_rule["end_local"]))
                and time.fromisoformat(str(preference["allowed_start_time"]))
                <= local_at.timetz().replace(tzinfo=None)
                < time.fromisoformat(str(preference["allowed_end_time"]))
            ):
                raise ValueError("scheduled contact falls outside the local allowed window")
        else:
            if case["next_action_at"] is not None:
                raise ValueError("blocked or suppressed decision cannot schedule a contact")
            if suppression_rule is None and not (
                decision["decision_type"] == "contact_blocked"
                and decision["outcome"] == "block"
                and decision["rule_id"]
                in {"R-CONTACT-01", "R-CONTACT-02", "R-CEASE-01"}
            ):
                raise ValueError("blocked contact decision is inconsistent")

    contact_activity = [
        (
            str(cases_by_id[str(attempt["case_id"])]["account_id"]),
            datetime.fromisoformat(str(attempt["attempted_at"])),
        )
        for attempt in dataset["contact_attempt"]
        if attempt["outcome"] != "policy_blocked"
    ]
    scheduled_decisions = sorted(
        [
            (
                str(cases_by_id[case_id]["account_id"]),
                datetime.fromisoformat(str(cases_by_id[case_id]["next_action_at"])),
            )
            for case_id, rows in decisions_by_case.items()
            if rows[0]["decision_type"] == "contact_allowed"
        ]
        + contact_activity,
        key=lambda item: item[1],
    )
    cap = policy["rules"]["R-CONTACT-02"]
    cap_period = timedelta(days=cap["period_days"])
    for index, (account_id, scheduled_at) in enumerate(scheduled_decisions):
        in_window = sum(
            1
            for prior_account, prior_at in scheduled_decisions[:index]
            if prior_account == account_id
            and timedelta(0) <= scheduled_at - prior_at < cap_period
        )
        if in_window >= cap["max_attempts"]:
            raise ValueError("scheduled contacts exceed the rolling weekly account cap")

    attempts_by_case: dict[str, list[Row]] = {}
    allowed_contact_outcomes = {
        "connected",
        "no_answer",
        "voicemail",
        "invalid_contact",
        "refused",
        "dispute_raised",
        "policy_blocked",
    }
    for attempt in dataset["contact_attempt"]:
        case_id = str(attempt["case_id"])
        if case_id not in cases_by_id:
            raise ValueError("contact attempt references an unknown case")
        if attempt["outcome"] not in allowed_contact_outcomes:
            raise ValueError("contact attempt has an unsupported outcome")
        case = cases_by_id[case_id]
        preference = preferences_by_account[str(case["account_id"])]
        attempted_at = datetime.fromisoformat(str(attempt["attempted_at"]))
        local_at = attempted_at.astimezone(ZoneInfo(str(preference["timezone"])))
        attempt_date = local_at.date()
        if attempt_date != date.fromisoformat(str(case["opened_at"])[:10]):
            raise ValueError("contact attempt must follow the case-open event date")
        if attempt["channel"] != preference["preferred_channel"]:
            raise ValueError("contact attempt channel does not match the effective preference")
        active_from = date.fromisoformat(str(preference["effective_from"]))
        active_to = (
            date.fromisoformat(str(preference["effective_to"]))
            if preference["effective_to"] is not None
            else None
        )
        active_preference = active_from <= attempt_date and (
            active_to is None or active_to >= attempt_date
        )
        contact_rule = policy["rules"]["R-CONTACT-01"]
        local_clock = local_at.timetz().replace(tzinfo=None)
        within_window = (
            time.fromisoformat(str(contact_rule["start_local"]))
            <= local_clock
            < time.fromisoformat(str(contact_rule["end_local"]))
            and time.fromisoformat(str(preference["allowed_start_time"]))
            <= local_clock
            < time.fromisoformat(str(preference["allowed_end_time"]))
        )
        if attempt["outcome"] != "policy_blocked":
            suppression_rule = _suppression_rule_at(
                loans_by_id[str(case["loan_id"])],
                accounts_by_id[str(case["account_id"])],
                disputes_by_account.get(str(case["account_id"]), []),
                hardships_by_account.get(str(case["account_id"]), []),
                preference,
                attempt_date,
                policy,
            )
            if not active_preference or not within_window or suppression_rule is not None:
                raise ValueError("contact was recorded despite an active restriction")
            outcome_cycle = policy["rules"]["R-CONTACT-03"]["case_sequence_cycle"]
            case_sequence = int(case_id.rsplit("-", 1)[1])
            expected_outcome = outcome_cycle[(case_sequence - 1) % len(outcome_cycle)]
            if attempt["outcome"] != expected_outcome:
                raise ValueError("contact outcome does not follow the documented segment rule")
        attempts_by_case.setdefault(case_id, []).append(attempt)
    if set(attempts_by_case) != set(cases_by_id) or any(
        len(rows) != 1 for rows in attempts_by_case.values()
    ):
        raise ValueError("each collection case must have exactly one contact attempt record")

    promises_by_case: dict[str, list[Row]] = {}
    promises_by_id: dict[str, Row] = {}
    for promise in dataset["promise_to_pay"]:
        promise_id = str(promise["promise_id"])
        case_id = str(promise["case_id"])
        if case_id not in cases_by_id or promise_id in promises_by_id:
            raise ValueError("promise references an unknown case or duplicates an ID")
        case = cases_by_id[case_id]
        attempt = attempts_by_case[case_id][0]
        if attempt["outcome"] != "connected":
            raise ValueError("promise requires a connected contact attempt")
        recorded_at = datetime.fromisoformat(str(promise["recorded_at"]))
        if recorded_at != datetime.fromisoformat(str(attempt["attempted_at"])):
            raise ValueError("promise record time must match its contact attempt")
        loan_id = str(case["loan_id"])
        arrears_at_promise, _ = calculate_delinquency(
            grouped_installments[loan_id],
            allocations_by_loan.get(loan_id, []),
            payments_by_account.get(str(case["account_id"]), []),
            recorded_at.date(),
        )
        promise_policy = policy["rules"]["R-PROMISE-01"]
        expected_amount = (
            arrears_at_promise
            * int(promise_policy["amount_percent_of_arrears"])
            // 100
        )
        if (
            arrears_at_promise <= 0
            or int(promise["promised_amount"]) != max(1, expected_amount)
        ):
            raise ValueError("promise amount does not match verified promise-date arrears")
        expected_due_date = recorded_at.date() + timedelta(
            days=int(promise_policy["promise_due_days"])
        )
        if promise["promised_date"] != expected_due_date.isoformat():
            raise ValueError("promise due date does not match policy")
        if promise["status"] not in {
            "PENDING",
            "KEPT",
            "PARTIAL",
            "BROKEN",
            "CANCELLED",
        }:
            raise ValueError("promise has an unsupported lifecycle status")
        promises_by_id[promise_id] = promise
        promises_by_case.setdefault(case_id, []).append(promise)
    if any(len(rows) > 1 for rows in promises_by_case.values()):
        raise ValueError("generator may record at most one promise per case")

    reconciliation_pairs: set[tuple[str, str]] = set()
    reconciliations_by_promise: dict[str, list[Row]] = {}
    for reconciliation in dataset["promise_reconciliation"]:
        promise_id = str(reconciliation["promise_id"])
        payment_id = str(reconciliation["payment_id"])
        pair = (promise_id, payment_id)
        if pair in reconciliation_pairs:
            raise ValueError("duplicate promise-payment reconciliation")
        if promise_id not in promises_by_id or payment_id not in payment_ids:
            raise ValueError("promise reconciliation references an unknown parent")
        reconciliation_pairs.add(pair)
        reconciliations_by_promise.setdefault(promise_id, []).append(reconciliation)

    for promise_id, promise in promises_by_id.items():
        case = cases_by_id[str(promise["case_id"])]
        loan_id = str(case["loan_id"])
        recorded_at = datetime.fromisoformat(str(promise["recorded_at"]))
        due_date = date.fromisoformat(str(promise["promised_date"]))
        grace_end_date = due_date + timedelta(days=int(policy["reconcile"]["grace_days"]))
        preference = preferences_by_account[str(case["account_id"])]
        grace_end = datetime.combine(
            grace_end_date,
            time.max,
            tzinfo=ZoneInfo(str(preference["timezone"])),
        )
        eligible_amounts: dict[str, int] = {}
        for allocation in allocations_by_loan.get(loan_id, []):
            payment_id = str(allocation["payment_id"])
            payment = payments_by_id.get(payment_id)
            if payment is None or payment["status"] != "posted" or payment["posted_at"] is None:
                continue
            posted_at = datetime.fromisoformat(str(payment["posted_at"]))
            if (
                posted_at > recorded_at
                and posted_at <= grace_end
                and posted_at.date() <= AS_OF_DATE
            ):
                eligible_amounts[payment_id] = (
                    eligible_amounts.get(payment_id, 0)
                    + int(allocation["allocated_amount"])
                )
        actual_rows = reconciliations_by_promise.get(promise_id, [])
        actual_amounts = {
            str(row["payment_id"]): int(row["reconciled_amount"])
            for row in actual_rows
        }
        if actual_amounts != eligible_amounts:
            raise ValueError("promise reconciliation does not match eligible posted allocations")
        cumulative = 0
        kept_at: datetime | None = None
        for row in sorted(
            actual_rows,
            key=lambda item: datetime.fromisoformat(str(item["reconciled_at"])),
        ):
            payment_id = str(row["payment_id"])
            payment = payments_by_id[payment_id]
            posted_at = datetime.fromisoformat(str(payment["posted_at"]))
            if datetime.fromisoformat(str(row["reconciled_at"])) != posted_at:
                raise ValueError("promise reconciliation timestamp must match payment posting")
            reconciled_amount = int(row["reconciled_amount"])
            if reconciled_amount <= 0 or reconciled_amount > int(payment["amount"]):
                raise ValueError("promise reconciliation amount is invalid")
            cumulative += reconciled_amount
            kept_threshold = int(promise["promised_amount"]) * (
                100 - int(policy["reconcile"]["tolerance_pct"])
            )
            reached_kept_threshold = cumulative * 100 >= kept_threshold
            expected_match_status = (
                "excess"
                if cumulative > int(promise["promised_amount"])
                else "matched"
                if reached_kept_threshold
                else "partial"
            )
            if row["match_status"] != expected_match_status:
                raise ValueError("promise reconciliation match status is inconsistent")
            if reached_kept_threshold and kept_at is None:
                kept_at = posted_at
        if kept_at is not None:
            expected_status = "KEPT"
            expected_resolved_at = kept_at.isoformat()
        elif grace_end_date <= AS_OF_DATE:
            expected_status = _promise_outcome(
                cumulative,
                int(promise["promised_amount"]),
                int(policy["reconcile"]["tolerance_pct"]),
            )
            expected_resolved_at = grace_end.isoformat()
        else:
            expected_status = "PENDING"
            expected_resolved_at = None
        if (
            promise["status"] != expected_status
            or promise["resolved_at"] != expected_resolved_at
        ):
            raise ValueError("promise lifecycle outcome does not match payments and grace period")

    event_groups: dict[tuple[str, str], list[Row]] = {}
    for event in dataset["state_event"]:
        event_case_id = event["case_id"]
        event_promise_id = event["promise_id"]
        if event["entity_type"] == "collection_case":
            if (
                event_case_id is None
                or event_promise_id is not None
                or str(event_case_id) not in cases_by_id
            ):
                raise ValueError("case state event has invalid target references")
            key = ("collection_case", str(event_case_id))
        elif event["entity_type"] == "promise_to_pay":
            if (
                event_promise_id is None
                or event_case_id is not None
                or str(event_promise_id) not in promises_by_id
            ):
                raise ValueError("promise state event has invalid target references")
            key = ("promise_to_pay", str(event_promise_id))
        else:
            raise ValueError("state event has an unknown entity type")
        event_groups.setdefault(key, []).append(event)

    expected_event_keys = {
        *(("collection_case", case_id) for case_id in cases_by_id),
        *(("promise_to_pay", promise_id) for promise_id in promises_by_id),
    }
    if set(event_groups) != expected_event_keys:
        raise ValueError("each case and promise must have a state-event lifecycle")
    for (entity_type, entity_id), rows in event_groups.items():
        rows.sort(key=lambda row: datetime.fromisoformat(str(row["changed_at"])))
        previous: str | None = None
        for index, event in enumerate(rows):
            state = str(event["new_state"])
            if event["previous_state"] != previous:
                raise ValueError("state event previous_state breaks lifecycle continuity")
            if entity_type == "collection_case":
                allowed_next = (
                    {"open", "paused", "resolved", "closed"}
                    if previous is None
                    else {
                        "open": {"paused", "resolved", "closed"},
                        "paused": {"open", "resolved", "closed"},
                        "resolved": (
                            {"closed", "open"}
                            if event["reason_code"] == "CASE_REOPENED"
                            else {"closed"}
                        ),
                        "closed": set(),
                    }.get(previous, set())
                )
            else:
                allowed_next = (
                    {"PENDING"}
                    if previous is None
                    else {"KEPT", "PARTIAL", "BROKEN", "CANCELLED"}
                    if previous == "PENDING"
                    else set()
                )
            if state not in allowed_next or state == previous:
                raise ValueError("state event violates the lifecycle transition rules")
            if index and datetime.fromisoformat(str(event["changed_at"])) < datetime.fromisoformat(
                str(rows[index - 1]["changed_at"])
            ):
                raise ValueError("state event timestamps are not chronological")
            previous = state
        final_record_state = (
            str(cases_by_id[entity_id]["status"])
            if entity_type == "collection_case"
            else str(promises_by_id[entity_id]["status"])
        )
        if previous != final_record_state:
            raise ValueError("state event lifecycle does not match the current record state")

    for loan_id in loan_ids:
        expected_opened_at = _first_threshold_crossing_date(
            grouped_installments[loan_id],
            allocations_by_loan.get(loan_id, []),
            payments_by_account.get(str(loans_by_id[loan_id]["account_id"]), []),
            AS_OF_DATE,
            threshold_days,
        )
        if (expected_opened_at is not None) != (loan_id in cases_by_loan):
            raise ValueError("collection case coverage does not match threshold crossings")
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


def write_dataset(
    dataset: Dataset,
    output_dir: Path,
    ground_truth: list[Row] | None = None,
    expected_decisions: list[Row] | None = None,
    *,
    seed: int = DEFAULT_SEED,
    dataset_name: str = "full",
) -> None:
    """Write reproducible CSV, JSON, SQL and manifest exports."""
    if dataset_name not in {"full", "starter"}:
        raise ValueError("dataset_name must be 'full' or 'starter'")
    data_dir = output_dir / "data" / dataset_name
    ground_truth_dir = output_dir / "ground_truth" / dataset_name
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
    ground_truth_columns = (
        "scenario_id",
        "issue_type",
        "entity_type",
        "entity_id",
        "is_primary",
        "rule_id",
        "expected_decision",
        "related_ids",
        "details",
    )
    with (ground_truth_dir / "ground_truth.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.DictWriter(
            output, fieldnames=ground_truth_columns, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(ground_truth or [])
    expected_decision_columns = (
        "scenario_id",
        "issue_type",
        "case_id",
        "loan_id",
        "expected_decision",
        "rule_id",
        "details",
    )
    with (ground_truth_dir / "expected_decisions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=expected_decision_columns,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(expected_decisions or [])

    input_dataset = {
        table: rows for table, rows in dataset.items() if table != "latent_segments"
    }
    json_path = data_dir / "dataset.json"
    with json_path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(input_dataset, output, ensure_ascii=True, separators=(",", ":"))
        output.write("\n")

    table_order = (
        "customer",
        "account",
        "loan",
        "installment",
        "contact_preference",
        "dispute",
        "hardship_request",
        "payment",
        "payment_allocation",
        "delinquency_snapshot",
        "collection_case",
        "decision_log",
        "contact_attempt",
        "promise_to_pay",
        "promise_reconciliation",
        "state_event",
    )
    sql_path = data_dir / "seed.sql"
    with sql_path.open("w", encoding="utf-8", newline="\n") as output:
        output.write("-- Generated synthetic seed data; see manifest.json for provenance.\n")
        output.write("BEGIN;\n")
        for table in table_order:
            columns = CSV_COLUMNS[table]
            rows = dataset[table]
            quoted_columns = ", ".join(f'"{column}"' for column in columns)
            for start in range(0, len(rows), 250):
                output.write(
                    f'INSERT INTO "{table}" ({quoted_columns}) VALUES\n'
                )
                batch = rows[start : start + 250]
                for index, row in enumerate(batch):
                    values = ", ".join(_sql_literal(row[column]) for column in columns)
                    suffix = "," if index < len(batch) - 1 else ";"
                    output.write(f"({values}){suffix}\n")
        output.write("COMMIT;\n")

    data_artifacts = sorted(
        [
            *data_dir.glob("*.csv"),
            json_path,
            sql_path,
        ],
        key=lambda path: path.name,
    )
    ground_truth_artifacts = sorted(ground_truth_dir.glob("*.csv"))
    scenario_issue_types = {
        str(row["issue_type"])
        for row in ground_truth or []
        if row["issue_type"] != "derived_recalculation"
    }
    anomaly_counts = {
        issue_type: sum(
            row["issue_type"] == issue_type for row in ground_truth or []
        )
        for issue_type in scenario_issue_types
    }
    manifest = {
        "dataset": dataset_name,
        "seed": seed,
        "loans": len(dataset["loan"]),
        "as_of_date": AS_OF_DATE.isoformat(),
        "generation_date": GENERATION_DATE.isoformat(),
        "anomaly_rows_per_type": max(anomaly_counts.values(), default=0),
        "source": {
            "type": "synthetic",
            "external_data_used": False,
            "generator": "yottaflex-debt-collection-engine",
        },
        "row_counts": {table: len(rows) for table, rows in input_dataset.items()},
        "ground_truth_row_counts": {
            "latent_segments": len(dataset["latent_segments"]),
            "ground_truth": len(ground_truth or []),
            "expected_decisions": len(expected_decisions or []),
        },
        "files": {
            path.name: _sha256_file(path) for path in data_artifacts
        },
        "ground_truth_files": {
            f"ground_truth/{dataset_name}/{path.name}": _sha256_file(path)
            for path in ground_truth_artifacts
        },
    }
    with (data_dir / "manifest.json").open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        json.dump(manifest, output, ensure_ascii=True, indent=2, sort_keys=True)
        output.write("\n")


def _sql_literal(value: str | int | bool | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    return "'" + value.replace("'", "''") + "'"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
