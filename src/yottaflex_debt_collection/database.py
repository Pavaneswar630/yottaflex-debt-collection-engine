"""Load generated CSV datasets into a foreign-key-enforced SQLite database."""

import argparse
import csv
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Sequence


TABLE_ORDER = (
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

INTEGER_COLUMNS = {
    ("loan", "principal_amount"),
    ("loan", "term_months"),
    ("installment", "sequence_number"),
    ("installment", "principal_due"),
    ("installment", "interest_due"),
    ("installment", "total_due"),
    ("delinquency_snapshot", "days_past_due"),
    ("delinquency_snapshot", "arrears_amount"),
    ("payment", "amount"),
    ("payment", "unapplied_amount"),
    ("payment_allocation", "allocated_amount"),
}
REAL_COLUMNS = {
    ("loan", "annual_interest_rate"),
    ("delinquency_snapshot", "risk_score"),
    ("collection_case", "priority_score"),
    ("collection_case", "balance_component"),
    ("collection_case", "age_component"),
    ("collection_case", "risk_component"),
    ("decision_log", "priority_score"),
}
BOOLEAN_COLUMNS = {("contact_preference", "do_not_contact")}
NULLABLE_COLUMNS = {
    ("account", "closed_at"),
    ("loan", "paid_off_date"),
    ("collection_case", "closed_at"),
    ("collection_case", "suppression_rule_id"),
    ("collection_case", "next_action_at"),
    ("contact_preference", "effective_to"),
    ("dispute", "resolved_at"),
    ("hardship_request", "resolved_at"),
    ("payment", "posted_at"),
    ("contact_attempt", "agent_id"),
    ("promise_to_pay", "resolved_at"),
    ("state_event", "case_id"),
    ("state_event", "promise_id"),
    ("state_event", "previous_state"),
}


def _convert_value(table: str, column: str, value: str | None) -> object:
    if value is None or value == "":
        if (table, column) in NULLABLE_COLUMNS:
            return None
        return value
    if (table, column) in INTEGER_COLUMNS:
        return int(value)
    if (table, column) in REAL_COLUMNS:
        return float(value)
    if (table, column) in BOOLEAN_COLUMNS:
        if value not in {"True", "False"}:
            raise ValueError(f"{table}.{column} must be True or False, got {value!r}")
        return int(value == "True")
    return value


def _read_rows(data_dir: Path, table: str) -> tuple[list[str], list[tuple[object, ...]]]:
    path = data_dir / f"{table}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Required dataset table is missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError(f"Dataset table has no header: {path}")
        columns = list(reader.fieldnames)
        rows = [
            tuple(_convert_value(table, column, row[column]) for column in columns)
            for row in reader
        ]
    return columns, rows


def _load_into_connection(
    connection: sqlite3.Connection,
    data_dir: Path,
    ground_truth_dir: Path | None,
) -> dict[str, int]:
    schema_path = Path(__file__).resolve().parents[2] / "schema" / "sqlite_schema.sql"
    if not schema_path.is_file():
        raise FileNotFoundError(f"SQLite schema is missing: {schema_path}")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    row_counts: dict[str, int] = {}
    with connection:
        for table in TABLE_ORDER:
            columns, rows = _read_rows(data_dir, table)
            column_sql = ", ".join(f'"{column}"' for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})',
                rows,
            )
            row_counts[table] = len(rows)
        if ground_truth_dir is not None:
            latent_path = ground_truth_dir / "latent_segments.csv"
            if latent_path.is_file():
                with latent_path.open(encoding="utf-8-sig", newline="") as source:
                    reader = csv.DictReader(source)
                    if set(reader.fieldnames or ()) != {"loan_id", "segment"}:
                        raise ValueError(
                            f"Unexpected latent-segment columns in {latent_path}"
                        )
                    latent_rows = [
                        (row["loan_id"], row["segment"]) for row in reader
                    ]
                connection.executemany(
                    "INSERT INTO latent_segment (loan_id, segment) VALUES (?, ?)",
                    latent_rows,
                )
                row_counts["latent_segment"] = len(latent_rows)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError(
                f"SQLite foreign-key check failed: {violations[:10]!r}"
            )
    return row_counts


def load_dataset(
    data_dir: Path | str,
    db_path: Path | str,
    ground_truth_dir: Path | str | None = None,
    *,
    overwrite: bool = False,
) -> dict[str, int]:
    """Create and populate a SQLite database from CSV exports.

    The existing database is left untouched if loading or FK validation fails.
    Replacing an existing database requires explicit ``overwrite=True``.
    """
    source_dir = Path(data_dir)
    target_path = Path(db_path)
    labels_dir = Path(ground_truth_dir) if ground_truth_dir is not None else None
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Dataset directory does not exist: {source_dir}")
    if target_path.exists() and not overwrite:
        raise FileExistsError(
            f"Database already exists: {target_path}; pass overwrite=True to replace it"
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{target_path.stem}-",
        suffix=".sqlite.tmp",
        dir=target_path.parent,
    )
    os.close(handle)
    temporary_path = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            row_counts = _load_into_connection(connection, source_dir, labels_dir)
        finally:
            connection.close()
        os.replace(temporary_path, target_path)
        return row_counts
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def connect_readonly(db_path: Path | str) -> sqlite3.Connection:
    """Open a query-only SQLite connection with foreign-key enforcement enabled."""
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA query_only = ON")
    return connection


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/full"))
    parser.add_argument("--ground-truth-dir", type=Path, default=Path("ground_truth/full"))
    parser.add_argument("--db", type=Path, default=Path("data/full/collection.sqlite"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    row_counts = load_dataset(
        args.data_dir,
        args.db,
        args.ground_truth_dir,
        overwrite=args.overwrite,
    )
    print(json.dumps({"database": str(args.db), "row_counts": row_counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
