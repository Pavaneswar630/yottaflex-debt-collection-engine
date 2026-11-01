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
        help="dataset root; writes data/ and ground_truth/ here (default: current directory)",
    )
    args = parser.parse_args(argv)
    if args.loans < 1:
        parser.error("--loans must be a positive integer")
    if args.seed < 0:
        parser.error("--seed must be a non-negative integer")
    dataset = generate_dataset(args.loans, args.seed, args.output_dir)
    print(
        f"Generated {len(dataset['loan'])} loans, "
        f"{len(dataset['installment'])} installments, "
        f"{len(dataset['payment'])} payments in {args.output_dir.resolve()}"
    )
    return 0
