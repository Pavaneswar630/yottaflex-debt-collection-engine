"""Tests for the YAML-sourced SQL and documentation artifacts."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SchemaGenerationTests(unittest.TestCase):
    def test_generated_artifacts_match_the_dictionary(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/generate_schema.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up to date", result.stdout)

    def test_dictionary_and_diagram_cover_schema_relationships(self) -> None:
        dictionary = (ROOT / "docs" / "DATA_DICTIONARY.md").read_text(
            encoding="utf-8"
        )
        diagram = (ROOT / "docs" / "ER_DIAGRAM.md").read_text(encoding="utf-8")
        sql = (ROOT / "schema" / "schema.sql").read_text(encoding="utf-8")

        for entity in (
            "customer",
            "account",
            "loan",
            "installment",
            "delinquency_snapshot",
            "contact_preference",
            "contact_attempt",
            "promise_to_pay",
            "payment",
            "collection_case",
            "payment_allocation",
        ):
            self.assertIn(f"### `{entity}`", dictionary)
            self.assertIn(f"    {entity.upper()} {{", diagram)
            self.assertIn(f"CREATE TABLE {entity} (", sql)

        self.assertIn("erDiagram", diagram)
        self.assertIn("PAYMENT ||--o{ PAYMENT_ALLOCATION", diagram)
        self.assertIn("INSTALLMENT ||--o{ PAYMENT_ALLOCATION", diagram)
        self.assertIn("Allowed values", dictionary)
        self.assertIn("Validation rule", dictionary)


if __name__ == "__main__":
    unittest.main()
