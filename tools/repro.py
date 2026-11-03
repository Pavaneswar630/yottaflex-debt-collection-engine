"""Regenerate a dataset twice and prove row-count and checksum reproducibility."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Sequence

from yottaflex_debt_collection.generator import generate_dataset
from yottaflex_debt_collection.settings import (
    AS_OF_DATE,
    DEFAULT_SEED,
    GENERATION_DATE,
)


def _file_checksums(root: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums[path.relative_to(root).as_posix()] = digest
    return checksums


def _render_summary(
    *,
    dataset_name: str,
    loans: int,
    seed: int,
    anomaly_rows: int,
    row_counts: dict[str, int],
    checksums: dict[str, str],
) -> str:
    lines = [
        "# Validation and reproducibility summary",
        "",
        "## Reproducibility proof",
        "",
        f"- Dataset: `{dataset_name}` ({loans:,} loans)",
        f"- Seed: `{seed}`",
        f"- Requested anomaly rows per type: `{anomaly_rows}`",
        f"- As-of date: `{AS_OF_DATE.isoformat()}`",
        f"- Generation date: `{GENERATION_DATE.isoformat()}`",
        "- Two independent generations produced identical relative file lists.",
        "- All exported file SHA-256 checksums matched across both generations.",
        "- Manifest input and ground-truth row counts matched across both generations.",
        "",
        "## Row counts",
        "",
        "| Table | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| `{table}` | {count:,} |" for table, count in sorted(row_counts.items()))
    lines.extend(
        [
            "",
            "## SHA-256 checksums",
            "",
            "| File | SHA-256 |",
            "|---|---|",
        ]
    )
    lines.extend(
        f"| `{path}` | `{checksum}` |"
        for path, checksum in sorted(checksums.items())
    )
    lines.append("")
    return "\n".join(lines)


def run_repro(
    *,
    loans: int = 10_000,
    seed: int = DEFAULT_SEED,
    anomaly_rows: int = 50,
    dataset_name: str = "full",
    report_path: Path | str | None = None,
) -> str:
    """Generate twice in isolated temporary roots and compare the full exports."""
    if loans < 1:
        raise ValueError("loans must be positive")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    if anomaly_rows < 0:
        raise ValueError("anomaly_rows must be non-negative")
    if dataset_name not in {"full", "starter"}:
        raise ValueError("dataset_name must be 'full' or 'starter'")

    with tempfile.TemporaryDirectory(prefix="yottaflex-repro-a-") as first_root_text:
        with tempfile.TemporaryDirectory(prefix="yottaflex-repro-b-") as second_root_text:
            first_root = Path(first_root_text)
            second_root = Path(second_root_text)
            for root in (first_root, second_root):
                generate_dataset(
                    loans,
                    seed,
                    root,
                    inject_anomalies=True,
                    anomaly_rows_per_type=anomaly_rows,
                    dataset_name=dataset_name,
                )
            first_checksums = _file_checksums(first_root)
            second_checksums = _file_checksums(second_root)
            if first_checksums != second_checksums:
                different = sorted(
                    path
                    for path in first_checksums.keys() | second_checksums.keys()
                    if first_checksums.get(path) != second_checksums.get(path)
                )
                raise AssertionError(
                    f"Generated exports differ between runs: {different[:20]}"
                )

            first_manifest_path = (
                first_root / "data" / dataset_name / "manifest.json"
            )
            second_manifest_path = (
                second_root / "data" / dataset_name / "manifest.json"
            )
            first_manifest = json.loads(first_manifest_path.read_text(encoding="utf-8"))
            second_manifest = json.loads(second_manifest_path.read_text(encoding="utf-8"))
            if first_manifest["row_counts"] != second_manifest["row_counts"]:
                raise AssertionError("Input table row counts differ between runs")
            if (
                first_manifest["ground_truth_row_counts"]
                != second_manifest["ground_truth_row_counts"]
            ):
                raise AssertionError("Ground-truth row counts differ between runs")

            report = _render_summary(
                dataset_name=dataset_name,
                loans=loans,
                seed=seed,
                anomaly_rows=anomaly_rows,
                row_counts=(
                    first_manifest["row_counts"]
                    | {
                        f"ground_truth.{name}": count
                        for name, count in first_manifest[
                            "ground_truth_row_counts"
                        ].items()
                    }
                ),
                checksums=first_checksums,
            )

    if report_path is not None:
        report_file = Path(report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8", newline="\n")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loans", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--anomaly-rows", type=int, default=50)
    parser.add_argument("--dataset", choices=("full", "starter"), default="full")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/validation_summary.md"),
    )
    args = parser.parse_args(argv)
    report = run_repro(
        loans=args.loans,
        seed=args.seed,
        anomaly_rows=args.anomaly_rows,
        dataset_name=args.dataset,
        report_path=args.report,
    )
    print(report)
    print(f"Reproducibility summary written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
