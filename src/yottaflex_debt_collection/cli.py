"""Command-line entry point for the debt-collection engine."""

import argparse


def main(argv: list[str] | None = None) -> int:
    """Run the scaffold CLI."""
    parser = argparse.ArgumentParser(
        prog="yottaflex-debt-collection",
        description="Synthetic, explainable debt-collection workflow scaffold.",
    )
    parser.parse_args(argv)
    return 0
