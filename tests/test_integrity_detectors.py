"""Tests for structural integrity checks and isolated detector evaluation."""

import ast
import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from yottaflex_debt_collection.detectors import DETECTOR_TYPES, detect
from yottaflex_debt_collection.evaluation import (
    render_report,
    score_detections,
)
from yottaflex_debt_collection.generator import generate_dataset
from yottaflex_debt_collection.integrity import validate_dataset_directory


ROOT = Path(__file__).resolve().parents[1]


class IntegrityAndDetectorTests(unittest.TestCase):
    def test_blind_detector_module_cannot_reference_label_locations(self) -> None:
        detector_source = (
            ROOT / "src" / "yottaflex_debt_collection" / "detectors.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(detector_source)
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        source_names = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        self.assertFalse(any("ground_truth" in module for module in imported_modules))
        self.assertNotIn("ground_truth", source_names)
        self.assertNotIn("evaluation", imported_modules)
        self.assertNotIn("ground_truth", detector_source.casefold())

    def test_integrity_checks_generated_files_and_detects_duplicate_key(self) -> None:
        with TemporaryDirectory() as output_dir:
            generate_dataset(
                40,
                20261022,
                output_dir,
                inject_anomalies=True,
                anomaly_rows_per_type=2,
                dataset_name="starter",
            )
            data_dir = Path(output_dir) / "data" / "starter"
            report = validate_dataset_directory(data_dir)
            self.assertTrue(report.valid, report.errors[:10])
            self.assertGreaterEqual(report.checks_passed, 6)
            self.assertEqual(report.row_counts["loan"], 40)

            customers_path = data_dir / "customer.csv"
            with customers_path.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
                headers = rows[0].keys()
            rows[1]["customer_id"] = rows[0]["customer_id"]
            with customers_path.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            invalid = validate_dataset_directory(data_dir)
            self.assertFalse(invalid.valid)
            self.assertTrue(any("duplicate primary key" in error for error in invalid.errors))

    def test_integrity_flags_foreign_key_enum_date_arithmetic_and_lifecycle_errors(self) -> None:
        with TemporaryDirectory() as output_dir:
            generate_dataset(20, 20261022, output_dir, dataset_name="starter")
            data_dir = Path(output_dir) / "data" / "starter"
            cases = (
                ("account.csv", "customer_id", "CUS-999999", "references missing"),
                ("loan.csv", "origination_date", "not-a-date", "invalid date/timestamp"),
                ("payment.csv", "status", "made_up", "invalid status"),
                ("installment.csv", "total_due", "1", "does not equal principal"),
                ("state_event.csv", "previous_state", "nonsense", "history is discontinuous"),
            )
            for filename, field, invalid_value, expected_message in cases:
                with self.subTest(table=filename, field=field):
                    path = data_dir / filename
                    original = path.read_bytes()
                    try:
                        with path.open(encoding="utf-8", newline="") as source:
                            reader = csv.DictReader(source)
                            headers = reader.fieldnames
                            rows = list(reader)
                        assert headers is not None
                        rows[0][field] = invalid_value
                        with path.open("w", encoding="utf-8", newline="") as output:
                            writer = csv.DictWriter(
                                output, fieldnames=headers, lineterminator="\n"
                            )
                            writer.writeheader()
                            writer.writerows(rows)
                        report = validate_dataset_directory(data_dir)
                        self.assertFalse(report.valid)
                        self.assertTrue(
                            any(expected_message in error for error in report.errors),
                            report.errors[:10],
                        )
                    finally:
                        path.write_bytes(original)

    def test_detectors_find_three_primary_issue_types_and_metrics(self) -> None:
        with TemporaryDirectory() as output_dir:
            generate_dataset(
                1_000,
                20261022,
                output_dir,
                inject_anomalies=True,
                anomaly_rows_per_type=5,
            )
            data_dir = Path(output_dir) / "data" / "full"
            labels_path = (
                Path(output_dir) / "ground_truth" / "full" / "ground_truth.csv"
            )
            with labels_path.open(encoding="utf-8", newline="") as source:
                labels = list(csv.DictReader(source))
            detections = detect(data_dir)
            truth_types = {
                row["issue_type"]
                for row in labels
                if row["is_primary"].casefold() == "true"
            }
            self.assertEqual(set(DETECTOR_TYPES), set(DETECTOR_TYPES) & truth_types)
            detected_types = {row["issue_type"] for row in detections}
            self.assertEqual(set(DETECTOR_TYPES), detected_types)
            scores = score_detections(detections, labels)
            for issue_type in DETECTOR_TYPES:
                with self.subTest(issue_type=issue_type):
                    self.assertGreater(scores[issue_type]["tp"], 0)
                    self.assertGreaterEqual(scores[issue_type]["recall"], 0.1)
                    self.assertTrue(0 <= scores[issue_type]["precision"] <= 1)
                    self.assertTrue(0 <= scores[issue_type]["f1"] <= 1)
            report = render_report(scores)
            self.assertIn("| Precision | Recall | F1 |", report)
            self.assertTrue(all(issue in report for issue in DETECTOR_TYPES))

    def test_clean_baseline_has_no_findings_for_initial_detector_types(self) -> None:
        with TemporaryDirectory() as output_dir:
            generate_dataset(1_000, 20261022, output_dir)
            detections = detect(Path(output_dir) / "data" / "full")
            self.assertEqual(detections, [])

    def test_minimum_coverage_for_normal_boundary_failure_and_exception(self) -> None:
        with TemporaryDirectory() as output_dir:
            dataset = generate_dataset(
                1_000,
                20261022,
                output_dir,
                inject_anomalies=True,
                anomaly_rows_per_type=5,
            )
            labels_path = (
                Path(output_dir) / "ground_truth" / "full" / "ground_truth.csv"
            )
            with labels_path.open(encoding="utf-8", newline="") as source:
                labels = list(csv.DictReader(source))
            primary = [
                row for row in labels if row["is_primary"].casefold() == "true"
            ]
            by_type: dict[str, int] = {}
            for row in primary:
                by_type[row["issue_type"]] = by_type.get(row["issue_type"], 0) + 1
            cases_with_exception = {
                row["related_ids"].split("|", maxsplit=1)[0]
                for row in primary
                if row["related_ids"]
            }
            normal_cases = [
                row
                for row in dataset["collection_case"]
                if row["case_id"] not in cases_with_exception
            ]
            boundary_types = (
                "near_miss_contact_at_0800",
                "near_miss_promise_equals_arrears",
            )
            failure_types = (
                "contact_outside_allowed_window",
                "payment_allocated_to_wrong_installment",
                "promise_exceeds_arrears",
            )
            exception_types = (
                "paid_account_in_collection",
                "disputed_debt_treated_as_confirmed",
            )
            self.assertGreaterEqual(len(normal_cases), 1)
            for label, issue_types in (
                ("boundary", boundary_types),
                ("failure", failure_types),
                ("exception", exception_types),
            ):
                for issue_type in issue_types:
                    with self.subTest(coverage=label, issue_type=issue_type):
                        self.assertGreaterEqual(by_type.get(issue_type, 0), 5)


if __name__ == "__main__":
    unittest.main()
