"""Tests for the isolated two-run reproducibility command."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.repro import run_repro


class ReproTests(unittest.TestCase):
    def test_repro_compares_exports_and_writes_checksum_proof(self) -> None:
        with TemporaryDirectory() as output_dir:
            report_path = Path(output_dir) / "validation_summary.md"
            report = run_repro(
                loans=80,
                seed=20261022,
                anomaly_rows=2,
                dataset_name="starter",
                report_path=report_path,
            )
            self.assertEqual(report, report_path.read_text(encoding="utf-8"))
            self.assertIn("Two independent generations produced identical", report)
            self.assertIn("All exported file SHA-256 checksums matched", report)
            self.assertIn("`data/starter/manifest.json`", report)
            self.assertIn("`ground_truth/starter/ground_truth.csv`", report)
            self.assertIn("| `loan` | 80 |", report)


if __name__ == "__main__":
    unittest.main()
