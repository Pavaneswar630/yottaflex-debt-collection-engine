"""Score blind detector outputs against a separately supplied label file."""

import argparse
import csv
import json
from pathlib import Path
from typing import Sequence

from yottaflex_debt_collection.detectors import DETECTOR_TYPES


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required evaluation CSV is missing: {path}")
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _truth_entity_id(row: dict[str, str]) -> str:
    value = row["entity_id"]
    if row["entity_type"] == "payment_allocation" and "->" in value:
        payment_id, target = value.split("|", 1)
        _, target_installment_id = target.split("->", 1)
        return f"{payment_id}|{target_installment_id}"
    return value


def score_detections(
    detections: list[dict[str, str]],
    ground_truth: list[dict[str, str]],
) -> dict[str, dict[str, int | float]]:
    """Compute per-type precision, recall and F1 using primary labels only."""
    truth = {
        (
            row["issue_type"],
            row["entity_type"],
            _truth_entity_id(row),
        )
        for row in ground_truth
        if row.get("is_primary", "").casefold() == "true"
        and row.get("issue_type") in DETECTOR_TYPES
    }
    predictions = {
        (
            row["issue_type"],
            row["entity_type"],
            row["entity_id"],
        )
        for row in detections
        if row.get("issue_type") in DETECTOR_TYPES
    }
    scores: dict[str, dict[str, int | float]] = {}
    for detector_type in DETECTOR_TYPES:
        type_truth = {row for row in truth if row[0] == detector_type}
        type_predictions = {row for row in predictions if row[0] == detector_type}
        true_positives = len(type_truth & type_predictions)
        false_positives = len(type_predictions - type_truth)
        false_negatives = len(type_truth - type_predictions)
        precision = (
            true_positives / (true_positives + false_positives)
            if true_positives + false_positives
            else 0.0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if true_positives + false_negatives
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        scores[detector_type] = {
            "tp": true_positives,
            "fp": false_positives,
            "fn": false_negatives,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return scores


def render_report(
    scores: dict[str, dict[str, int | float]],
    metadata: dict[str, object] | None = None,
) -> str:
    lines = [
        "# Blind detector evaluation",
        "",
        "Scores compare detector output with primary labels; derived recalculation rows are excluded.",
    ]
    if metadata:
        lines.extend(
            [
                "",
                "Dataset: "
                f"`{metadata.get('dataset', 'unknown')}`; "
                f"loans: {metadata.get('loans', 'unknown')}; "
                f"seed: {metadata.get('seed', 'unknown')}.",
            ]
        )
    lines.extend(
        [
            "",
            "| Issue type | TP | FP | FN | Precision | Recall | F1 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for detector_type in DETECTOR_TYPES:
        row = scores[detector_type]
        lines.append(
            f"| {detector_type} | {row['tp']} | {row['fp']} | {row['fn']} | "
            f"{row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--detections", type=Path, default=Path("reports/detections.csv"))
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("ground_truth/full/ground_truth.csv"),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--report", type=Path, default=Path("reports/detector_metrics.md"))
    args = parser.parse_args(argv)
    manifest_path = args.manifest or (
        args.ground_truth.parent.parent.parent
        / "data"
        / args.ground_truth.parent.name
        / "manifest.json"
    )
    metadata = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else None
    )
    scores = score_detections(
        _read_csv(args.detections),
        _read_csv(args.ground_truth),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(scores, metadata), encoding="utf-8")
    print(json.dumps(scores, indent=2))
    print(f"Metrics report written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
