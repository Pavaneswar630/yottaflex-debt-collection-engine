"""Print representative queue, suppression, and blocked-contact records."""

import argparse
from pathlib import Path
from typing import Sequence

from yottaflex_debt_collection.database import connect_readonly


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def run_demo(database_path: Path) -> str:
    """Return a short deterministic walkthrough backed by the local SQLite data."""
    connection = connect_readonly(database_path)
    try:
        queue = connection.execute(
            """
            SELECT case_id, priority_tier, priority_score, days_past_due, arrears_amount
            FROM priority_queue
            ORDER BY priority_score DESC, case_id
            LIMIT 5
            """
        ).fetchall()
        if not queue:
            raise ValueError("The priority queue is empty; generate and load a dataset first")

        suppressed = connection.execute(
            """
            SELECT case_id, status, suppression_rule_id, priority_score
            FROM collection_case
            WHERE status = 'paused' AND suppression_rule_id IS NOT NULL
            ORDER BY case_id
            LIMIT 1
            """
        ).fetchone()
        if suppressed is None:
            raise ValueError("No paused, suppressed case is available for the demo")

        blocked = connection.execute(
            """
            SELECT case_id, rule_id, outcome, reason
            FROM decision_log
            WHERE outcome = 'block' OR decision_type = 'contact_blocked'
            ORDER BY as_of_date DESC, decision_id
            LIMIT 1
            """
        ).fetchone()
        if blocked is None:
            raise ValueError("No blocked-contact decision is available for the demo")

        lines = [
            "Yottaflex policy-aware collections demo (synthetic records only)",
            "",
            "Priority queue - highest recorded scores:",
            "CASE ID             TIER  SCORE   DPD  ARREARS",
        ]
        lines.extend(
            f"{row['case_id']:<19} {row['priority_tier']:<4} "
            f"{row['priority_score']:>5.1f} {row['days_past_due']:>5} "
            f"{_money(row['arrears_amount'])}"
            for row in queue
        )
        lines.extend(
            [
                "",
                "Suppressed case - retained for traceability, not queued for contact:",
                f"{suppressed['case_id']} status={suppressed['status']} "
                f"rule={suppressed['suppression_rule_id']} "
                f"score={suppressed['priority_score']:.1f}",
                "",
                "Blocked contact - recorded policy decision:",
                f"{blocked['case_id']} rule={blocked['rule_id']} "
                f"outcome={blocked['outcome']}: {blocked['reason']}",
                "",
                "No contacts are sent or scheduled by this demo.",
            ]
        )
        return "\n".join(lines)
    finally:
        connection.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/full/collection.sqlite"),
        help="loaded SQLite database (default: data/full/collection.sqlite)",
    )
    args = parser.parse_args(argv)
    print(run_demo(args.db))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
