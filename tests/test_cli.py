"""Smoke tests for the scaffold command-line entry point."""

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from yottaflex_debt_collection.cli import main


class CliTests(unittest.TestCase):
    def test_cli_generates_requested_dataset(self) -> None:
        with TemporaryDirectory() as output_dir:
            self.assertEqual(
                main(["--loans", "2", "--seed", "17", "--output-dir", output_dir]),
                0,
            )
            self.assertTrue(
                (Path(output_dir) / "ground_truth" / "latent_segments.csv").is_file()
            )


if __name__ == "__main__":
    unittest.main()
