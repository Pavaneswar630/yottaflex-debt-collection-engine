"""Command-line entry point for the debt-collection engine."""

import argparse
from pathlib import Path

from yottaflex_debt_collection.generator import generate_dataset
from yottaflex_debt_collection.settings import DEFAULT_SEED


def main(argv: list[str] | None = None) -> int:
    """Generate a reproducible synthetic dataset from command-line options."""
    parser = argparse.ArgumentParser(
        prog="yottaflex-debt-collection",
        description="Generate synthetic debt-collection CSVs and isolated ground truth.",
    )
    parser.add_argument(
        "--loans",
        type=int,
        default=10_000,
        help="number of loans to generate (default: 10000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"non-negative NumPy seed (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="output root; writes data/<dataset>/ and ground_truth/<dataset>/ here",
    )
    parser.add_argument(
        "--dataset",
        choices=("full", "starter"),
        help="output dataset name (defaults to starter for <=100 loans, otherwise full)",
    )
    parser.add_argument(
        "--anomaly-rows",
        type=int,
        default=50,
        help="maximum labeled examples per anomaly and near-miss type (default: 50)",
    )
    args = parser.parse_args(argv)
    if args.loans < 1:
        parser.error("--loans must be a positive integer")
    if args.seed < 0:
        parser.error("--seed must be a non-negative integer")
    if args.anomaly_rows < 0:
        parser.error("--anomaly-rows must be non-negative")
    dataset_name = args.dataset or ("starter" if args.loans <= 100 else "full")
    dataset = generate_dataset(
        args.loans,
        args.seed,
        args.output_dir,
        inject_anomalies=True,
        anomaly_rows_per_type=args.anomaly_rows,
        dataset_name=dataset_name,
    )
    print(
        f"Generated {len(dataset['loan'])} loans, "
        f"{len(dataset['installment'])} installments, "
        f"{len(dataset['payment'])} payments in "
        f"{(args.output_dir / 'data' / dataset_name).resolve()}"
    )
    return 0
