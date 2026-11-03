"""Generate deterministic README charts from exported data and reports.

The latent-segment and primary-label files are read only for these reporting
visualizations; neither is used as an input feature or by a detector.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
BUCKETS = ("current", "1_30", "31_60", "61_90", "90_plus")
BUCKET_LABELS = ("Current", "1-30", "31-60", "61-90", "90+")
DETECTOR_TYPES = (
    "paid_account_in_collection",
    "contact_outside_allowed_window",
    "payment_allocated_to_wrong_installment",
)
PROMISE_STATUSES = ("KEPT", "PARTIAL", "BROKEN")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required chart input is missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def open_database(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(
            f"SQLite database is missing: {path}; run the db-load target first"
        )
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def save_figure(figure: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=160,
        bbox_inches="tight",
        facecolor="white",
        metadata={"Software": "make_readme_assets.py"},
    )
    plt.close(figure)


def delinquency_bucket(days_past_due: int) -> str:
    if days_past_due == 0:
        return "current"
    if days_past_due <= 30:
        return "1_30"
    if days_past_due <= 60:
        return "31_60"
    if days_past_due <= 90:
        return "61_90"
    return "90_plus"


def plot_dpd_distribution(
    connection: sqlite3.Connection, as_of_date: str, output_dir: Path
) -> None:
    rows = connection.execute(
        "SELECT snapshot_date, days_past_due FROM latest_snapshot ORDER BY loan_id"
    ).fetchall()
    dates = {row["snapshot_date"] for row in rows}
    if dates != {as_of_date}:
        raise ValueError(
            f"Latest snapshot dates {sorted(dates)} do not match manifest as-of date "
            f"{as_of_date}"
        )
    counts = Counter(delinquency_bucket(int(row["days_past_due"])) for row in rows)
    values = [counts[bucket] for bucket in BUCKETS]
    figure, axis = plt.subplots(figsize=(8, 4.8))
    bars = axis.bar(BUCKET_LABELS, values, color="#4472C4")
    axis.bar_label(bars, fmt="%.0f", padding=3, fontsize=9)
    axis.set(
        title=f"Loan delinquency as of {as_of_date}",
        xlabel="Days past due",
        ylabel="Loans",
    )
    axis.set_ylim(0, max(values, default=0) * 1.14 or 1)
    axis.grid(axis="y", alpha=0.25)
    save_figure(figure, output_dir / "dpd_distribution.png")


def plot_roll_rates(connection: sqlite3.Connection, output_dir: Path) -> None:
    counts = {
        (row["from_bucket"], row["to_bucket"]): int(row["loan_transitions"])
        for row in connection.execute(
            "SELECT from_bucket, to_bucket, loan_transitions FROM roll_rates"
        )
    }
    matrix = [[0.0 for _ in BUCKETS] for _ in BUCKETS]
    for row_index, source in enumerate(BUCKETS):
        source_total = sum(counts.get((source, target), 0) for target in BUCKETS)
        if source_total:
            for column_index, target in enumerate(BUCKETS):
                matrix[row_index][column_index] = (
                    100 * counts.get((source, target), 0) / source_total
                )
    figure, axis = plt.subplots(figsize=(8, 6))
    image = axis.imshow(matrix, cmap="Blues", vmin=0, vmax=100)
    axis.set_xticks(range(len(BUCKETS)), BUCKET_LABELS)
    axis.set_yticks(range(len(BUCKETS)), BUCKET_LABELS)
    axis.set(
        title="Month-end delinquency roll rates",
        xlabel="Next month bucket",
        ylabel="Previous month bucket",
    )
    for row in range(len(BUCKETS)):
        for column in range(len(BUCKETS)):
            color = "white" if matrix[row][column] >= 55 else "#1F2937"
            axis.text(
                column,
                row,
                f"{matrix[row][column]:.1f}%",
                ha="center",
                va="center",
                color=color,
                fontsize=9,
            )
    figure.colorbar(image, ax=axis, label="Share of transitions from source bucket (%)")
    save_figure(figure, output_dir / "roll_rates.png")


def plot_priority_tiers(connection: sqlite3.Connection, output_dir: Path) -> None:
    rows = connection.execute(
        "SELECT priority_score FROM collection_case ORDER BY case_id"
    ).fetchall()
    scores = [float(row["priority_score"]) for row in rows]
    figure, axis = plt.subplots(figsize=(8, 4.8))
    axis.hist(scores, bins=20, color="#4F9D69", edgecolor="white")
    axis.axvline(40, color="#E69F00", linestyle="--", linewidth=2, label="P2 threshold (40)")
    axis.axvline(70, color="#C43C39", linestyle="--", linewidth=2, label="P1 threshold (70)")
    axis.set(
        title="Collection case priority-score distribution",
        xlabel="Priority score",
        ylabel="Cases",
    )
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.25)
    save_figure(figure, output_dir / "priority_tiers.png")


def plot_promise_outcomes(
    connection: sqlite3.Connection, ground_truth_dir: Path, output_dir: Path
) -> None:
    # Latent segments come from ground_truth only to annotate this reporting chart.
    segment_by_loan = {
        row["loan_id"]: row["segment"]
        for row in read_csv(ground_truth_dir / "latent_segments.csv")
    }
    rows = connection.execute(
        """
        SELECT collection_case.loan_id, promise_to_pay.status
        FROM promise_to_pay
        JOIN collection_case
            ON collection_case.case_id = promise_to_pay.case_id
        ORDER BY promise_to_pay.promise_id
        """
    ).fetchall()
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        segment = segment_by_loan.get(row["loan_id"])
        if segment is None:
            raise ValueError(f"No latent reporting segment for loan {row['loan_id']}")
        if row["status"] not in PROMISE_STATUSES:
            raise ValueError(f"Unsupported resolved promise status: {row['status']}")
        counts[segment][row["status"]] += 1
    segments = sorted(counts)
    figure, axis = plt.subplots(figsize=(9, 5))
    bottoms = [0 for _ in segments]
    colors = {"KEPT": "#4F9D69", "PARTIAL": "#E69F00", "BROKEN": "#C43C39"}
    for status in PROMISE_STATUSES:
        values = [counts[segment][status] for segment in segments]
        axis.bar(segments, values, bottom=bottoms, label=status, color=colors[status])
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]
    axis.set(
        title="Promise outcomes by synthetic borrower segment",
        xlabel="Synthetic latent segment",
        ylabel="Promises",
    )
    axis.tick_params(axis="x", rotation=25)
    axis.legend(title="Recorded outcome", frameon=False)
    axis.grid(axis="y", alpha=0.2)
    save_figure(figure, output_dir / "promise_outcomes.png")


def plot_compliance_decisions(connection: sqlite3.Connection, output_dir: Path) -> None:
    rows = connection.execute(
        """
        SELECT decision_type, rule_id, COUNT(*) AS decision_count
        FROM decision_log
        GROUP BY decision_type, rule_id
        ORDER BY decision_type, rule_id
        """
    ).fetchall()
    decision_types = sorted({row["decision_type"] for row in rows})
    rules = sorted({row["rule_id"] for row in rows})
    counts = {
        (row["decision_type"], row["rule_id"]): int(row["decision_count"])
        for row in rows
    }
    figure, axis = plt.subplots(figsize=(10, 5.5))
    bottoms = [0 for _ in decision_types]
    palette = plt.get_cmap("tab20")
    for index, rule in enumerate(rules):
        values = [counts.get((kind, rule), 0) for kind in decision_types]
        if not any(values):
            continue
        axis.bar(
            decision_types,
            values,
            bottom=bottoms,
            label=rule,
            color=palette(index % 20),
        )
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]
    axis.set(
        title="Recorded contact and suppression decisions",
        xlabel="Decision type",
        ylabel="DecisionLog rows",
    )
    axis.tick_params(axis="x", rotation=20)
    axis.legend(title="Rule ID", frameon=False, bbox_to_anchor=(1.02, 1), loc="upper left")
    axis.grid(axis="y", alpha=0.2)
    save_figure(figure, output_dir / "compliance_decisions.png")


def normalize_truth_id(row: dict[str, str]) -> str:
    value = row["entity_id"]
    if row["entity_type"] == "payment_allocation" and "->" in value:
        payment_id, target = value.split("|", 1)
        _, target_installment_id = target.split("->", 1)
        return f"{payment_id}|{target_installment_id}"
    return value


def detector_scores(
    report_path: Path, ground_truth_dir: Path
) -> dict[str, dict[str, float]]:
    report_rows = read_csv(report_path)
    # Primary ground-truth labels are read exclusively for this offline report chart.
    primary_truth_rows = [
        row
        for row in read_csv(ground_truth_dir / "ground_truth.csv")
        if row["is_primary"].casefold() == "true"
        and row["issue_type"] in DETECTOR_TYPES
    ]
    truth = {
        (row["issue_type"], row["entity_type"], normalize_truth_id(row))
        for row in primary_truth_rows
    }
    predictions = {
        (row["issue_type"], row["entity_type"], row["entity_id"])
        for row in report_rows
        if row.get("issue_type") in DETECTOR_TYPES
    }
    scores: dict[str, dict[str, float]] = {}
    for issue_type in DETECTOR_TYPES:
        expected = {item for item in truth if item[0] == issue_type}
        predicted = {item for item in predictions if item[0] == issue_type}
        true_positive = len(expected & predicted)
        precision = true_positive / len(predicted) if predicted else 0.0
        recall = true_positive / len(expected) if expected else 0.0
        scores[issue_type] = {"precision": precision, "recall": recall}
    return scores


def plot_detector_pr(
    report_path: Path, ground_truth_dir: Path, output_dir: Path
) -> None:
    scores = detector_scores(report_path, ground_truth_dir)
    labels = [issue_type.replace("_", "\n") for issue_type in DETECTOR_TYPES]
    indices = list(range(len(labels)))
    width = 0.36
    figure, axis = plt.subplots(figsize=(10, 5))
    precision = [scores[issue_type]["precision"] for issue_type in DETECTOR_TYPES]
    recall = [scores[issue_type]["recall"] for issue_type in DETECTOR_TYPES]
    precision_bars = axis.bar(
        [index - width / 2 for index in indices],
        precision,
        width,
        label="Precision",
        color="#4472C4",
    )
    recall_bars = axis.bar(
        [index + width / 2 for index in indices],
        recall,
        width,
        label="Recall",
        color="#E69F00",
    )
    axis.bar_label(precision_bars, fmt="%.3f", padding=3, fontsize=8)
    axis.bar_label(recall_bars, fmt="%.3f", padding=3, fontsize=8)
    axis.set(
        title="Blind detector precision and recall",
        xlabel="Labeled anomaly type",
        ylabel="Score",
        ylim=(0, 1.15),
    )
    axis.set_xticks(indices, labels)
    axis.legend(frameon=False)
    axis.grid(axis="y", alpha=0.2)
    save_figure(figure, output_dir / "detector_pr.png")


def plot_anomaly_coverage(ground_truth_dir: Path, output_dir: Path) -> None:
    # Labels are read only to summarize injected scenarios in this reporting chart.
    primary = [
        row
        for row in read_csv(ground_truth_dir / "ground_truth.csv")
        if row["is_primary"].casefold() == "true"
    ]
    counts = Counter(row["issue_type"] for row in primary)
    issue_types = sorted(counts)
    colors = [
        "#C43C39" if not issue_type.startswith("near_miss_") else "#4472C4"
        for issue_type in issue_types
    ]
    figure, axis = plt.subplots(figsize=(10, 5.5))
    bars = axis.bar(
        [issue_type.replace("_", "\n") for issue_type in issue_types],
        [counts[issue_type] for issue_type in issue_types],
        color=colors,
    )
    axis.bar_label(bars, padding=3, fontsize=9)
    axis.set(
        title="Injected primary anomalies and valid near-misses",
        xlabel="Scenario type",
        ylabel="Labeled scenarios",
    )
    axis.tick_params(axis="x", labelsize=8)
    axis.grid(axis="y", alpha=0.2)
    save_figure(figure, output_dir / "anomaly_coverage.png")


def make_assets(
    data_dir: Path,
    database_path: Path,
    ground_truth_dir: Path,
    reports_dir: Path,
    output_dir: Path,
) -> list[Path]:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Dataset manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    as_of_date = manifest.get("as_of_date")
    if not isinstance(as_of_date, str) or not as_of_date:
        raise ValueError(f"Manifest has no valid as_of_date: {manifest_path}")
    snapshot_csv = data_dir / "delinquency_snapshot.csv"
    if not snapshot_csv.is_file():
        raise FileNotFoundError(f"Required chart input is missing: {snapshot_csv}")
    connection = open_database(database_path)
    try:
        plot_dpd_distribution(connection, as_of_date, output_dir)
        plot_roll_rates(connection, output_dir)
        plot_priority_tiers(connection, output_dir)
        plot_promise_outcomes(connection, ground_truth_dir, output_dir)
        plot_compliance_decisions(connection, output_dir)
    finally:
        connection.close()
    plot_detector_pr(reports_dir / "detections.csv", ground_truth_dir, output_dir)
    plot_anomaly_coverage(ground_truth_dir, output_dir)
    return [
        output_dir / name
        for name in (
            "dpd_distribution.png",
            "roll_rates.png",
            "priority_tiers.png",
            "promise_outcomes.png",
            "compliance_decisions.png",
            "detector_pr.png",
            "anomaly_coverage.png",
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "full")
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data" / "full" / "collection.sqlite"
    )
    parser.add_argument(
        "--ground-truth-dir", type=Path, default=ROOT / "ground_truth" / "full"
    )
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "img")
    args = parser.parse_args()
    outputs = make_assets(
        args.data_dir,
        args.db,
        args.ground_truth_dir,
        args.reports_dir,
        args.output_dir,
    )
    for path in outputs:
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
