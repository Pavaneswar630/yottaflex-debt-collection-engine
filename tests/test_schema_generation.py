"""Tests for the YAML-sourced SQL and documentation artifacts."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


class SchemaGenerationTests(unittest.TestCase):
    def test_generated_artifacts_match_the_dictionary(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/generate_schema.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("up to date", result.stdout)

    def test_dictionary_and_cardinality_documentation_cover_schema(self) -> None:
        dictionary = (ROOT / "docs" / "DATA_DICTIONARY.md").read_text(
            encoding="utf-8"
        )
        sql = (ROOT / "schema" / "schema.sql").read_text(encoding="utf-8")
        er = (ROOT / "docs" / "ER.md").read_text(encoding="utf-8")

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
            "promise_reconciliation",
            "case_state_history",
            "decision_log",
            "state_event",
            "dispute",
            "hardship_request",
        ):
            self.assertIn(f"### `{entity}`", dictionary)
            self.assertIn(f"CREATE TABLE {entity} (", sql)

        self.assertIn("erDiagram", er)
        self.assertIn("Loan → CollectionCase", er)
        self.assertIn("0..1 loan", er)
        self.assertIn("PAYMENT ||--o{ PAYMENT_ALLOCATION", er)
        self.assertIn("INSTALLMENT ||--o{ PAYMENT_ALLOCATION", er)
        self.assertIn("Allowed values", dictionary)
        self.assertIn("Validation rule", dictionary)

    def test_dictionary_fields_have_the_required_named_shape(self) -> None:
        with (ROOT / "schema" / "data_dictionary.yaml").open(
            encoding="utf-8"
        ) as source_file:
            data_dictionary = yaml.safe_load(source_file)

        required_keys = {
            "name",
            "type",
            "required",
            "allowed_values",
            "unit",
            "unique",
            "validation",
        }
        entities = {table["name"]: table for table in data_dictionary["tables"]}
        self.assertEqual(len(entities), 17)
        for table_name, table in entities.items():
            for field_name, field in table["fields"].items():
                with self.subTest(table=table_name, field=field_name):
                    self.assertTrue(required_keys <= field.keys())
                    self.assertEqual(field["name"], field_name)
                    self.assertIsInstance(field["allowed_values"], list)
                    self.assertIsInstance(field["required"], bool)
                    self.assertIsInstance(field["unique"], bool)

        self.assertTrue(
            {
                "payment_allocation",
                "promise_reconciliation",
                "case_state_history",
                "decision_log",
                "state_event",
                "dispute",
                "hardship_request",
            }
            <= entities.keys()
        )
        self.assertIn("effective_from", entities["contact_preference"]["fields"])
        self.assertIn("effective_to", entities["contact_preference"]["fields"])

    def test_handwritten_sql_has_fk_constraints_checks_and_fk_indexes(self) -> None:
        with (ROOT / "schema" / "data_dictionary.yaml").open(
            encoding="utf-8"
        ) as source_file:
            data_dictionary = yaml.safe_load(source_file)
        sql = (ROOT / "schema" / "schema.sql").read_text(encoding="utf-8")

        self.assertIn("-- Hand-maintained PostgreSQL DDL.", sql)
        for table in data_dictionary["tables"]:
            table_name = table["name"]
            match = re.search(
                rf"CREATE TABLE {table_name} \((.*?)\n\);",
                sql,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match, f"Missing SQL table {table_name}")
            table_sql = match.group(1)
            primary_key = [
                name
                for name, field in table["fields"].items()
                if field.get("primary_key")
            ]
            self.assertTrue(primary_key, f"No primary key defined for {table_name}")
            self.assertIn(
                f"PRIMARY KEY ({', '.join(primary_key)})",
                table_sql,
                f"SQL primary key mismatch for {table_name}",
            )
            for field_name, field in table["fields"].items():
                sql_type = re.escape(field["type"])
                nullable = r" NOT NULL" if field["required"] else ""
                self.assertIsNotNone(
                    re.search(
                        rf"^\s+{field_name} {sql_type}{nullable},?$",
                        table_sql,
                        flags=re.MULTILINE,
                    ),
                    f"SQL column mismatch for {table_name}.{field_name}",
                )
                if field.get("references"):
                    reference = field["references"]
                    self.assertRegex(
                        table_sql,
                        rf"FOREIGN KEY\s*\({field_name}\)\s+REFERENCES\s+"
                        rf"{reference['table']}\s+\({reference['field']}\)",
                    )
                    self.assertRegex(
                        sql,
                        rf"CREATE (?:UNIQUE )?INDEX \w+\s+ON {table_name}\s+"
                        rf"\({field_name}\)",
                    )
                if field["allowed_values"]:
                    self.assertRegex(
                        table_sql,
                        rf"CHECK\s*\([^;]*\b{field_name}\s+IN\s*\(",
                    )

    def test_money_columns_are_integer_cents(self) -> None:
        with (ROOT / "schema" / "data_dictionary.yaml").open(
            encoding="utf-8"
        ) as source_file:
            data_dictionary = yaml.safe_load(source_file)

        monetary_fields = {
            "loan": ("principal_amount",),
            "installment": ("principal_due", "interest_due", "total_due"),
            "delinquency_snapshot": ("arrears_amount",),
            "promise_to_pay": ("promised_amount",),
            "payment": ("amount", "unapplied_amount"),
            "payment_allocation": ("allocated_amount",),
        }
        tables = {table["name"]: table for table in data_dictionary["tables"]}
        for table_name, field_names in monetary_fields.items():
            fields = tables[table_name]["fields"]
            for field_name in field_names:
                with self.subTest(table=table_name, field=field_name):
                    self.assertEqual(fields[field_name]["type"], "BIGINT")
                    self.assertEqual(fields[field_name]["unit"], "integer cents")


if __name__ == "__main__":
    unittest.main()
