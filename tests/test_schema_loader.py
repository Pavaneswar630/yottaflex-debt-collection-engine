"""Tests for the Pydantic data-dictionary loader."""

import unittest

from pydantic import ValidationError

from yottaflex_debt_collection.schema_loader import DataDictionary, load_dictionary


class SchemaLoaderTests(unittest.TestCase):
    def test_repository_dictionary_validates(self) -> None:
        dictionary = load_dictionary()
        self.assertEqual(len(dictionary.tables), 14)
        self.assertEqual(dictionary.tables[0].name, "customer")

    def test_field_contract_requires_named_dictionary_attributes(self) -> None:
        minimal = {
            "schema_version": 1,
            "title": "test",
            "sql_dialect": "postgresql",
            "description": "test dictionary",
            "tables": [
                {
                    "name": "example",
                    "description": "example table",
                    "fields": {
                        "example_id": {
                            "name": "example_id",
                            "type": "VARCHAR(16)",
                            "required": True,
                            "allowed_values": [],
                            "unit": "none",
                            "unique": True,
                            "validation": "non-empty",
                        }
                    },
                }
            ],
        }
        self.assertEqual(len(DataDictionary.model_validate(minimal).tables), 1)
        del minimal["tables"][0]["fields"]["example_id"]["allowed_values"]
        with self.assertRaises(ValidationError):
            DataDictionary.model_validate(minimal)


if __name__ == "__main__":
    unittest.main()
