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
                (
                    Path(output_dir)
                    / "ground_truth"
                    / "starter"
                    / "latent_segments.csv"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(output_dir)
                    / "ground_truth"
                    / "starter"
                    / "ground_truth.csv"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(output_dir)
                    / "ground_truth"
                    / "starter"
                    / "expected_decisions.csv"
                ).is_file()
            )
            data_dir = Path(output_dir) / "data" / "starter"
            self.assertTrue((data_dir / "dataset.json").is_file())
            self.assertTrue((data_dir / "seed.sql").is_file())
            self.assertTrue((data_dir / "manifest.json").is_file())
            self.assertEqual(
                main(
                    [
                        "--dataset",
                        "full",
                        "--loans",
                        "2",
                        "--seed",
                        "17",
                        "--output-dir",
                        output_dir,
                        "--anomaly-rows",
                        "0",
                    ]
                ),
                0,
            )
            self.assertTrue((Path(output_dir) / "data" / "full" / "manifest.json").is_file())
            self.assertTrue(
                (
                    Path(output_dir)
                    / "ground_truth"
                    / "full"
                    / "expected_decisions.csv"
                ).is_file()
            )


if __name__ == "__main__":
    unittest.main()
