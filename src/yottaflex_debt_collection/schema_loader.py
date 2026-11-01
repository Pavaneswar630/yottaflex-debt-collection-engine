"""Pydantic-validated loader for the YAML data dictionary."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DICTIONARY = ROOT / "schema" / "data_dictionary.yaml"


class FieldDefinition(BaseModel):
    """Required field shape; schema-specific SQL metadata is preserved."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    required: bool
    allowed_values: list[str]
    unit: str
    unique: bool
    validation: str


class TableDefinition(BaseModel):
    """One named table and its field definitions."""

    model_config = ConfigDict(extra="allow")

    name: str
    description: str
    fields: dict[str, FieldDefinition]

    @model_validator(mode="after")
    def field_names_match_keys(self) -> "TableDefinition":
        for key, definition in self.fields.items():
            if definition.name != key:
                raise ValueError(f"{self.name}.{key}: field name must match mapping key")
        return self


class DataDictionary(BaseModel):
    """Top-level dictionary contract."""

    model_config = ConfigDict(extra="allow")

    schema_version: int
    title: str
    sql_dialect: str
    description: str
    tables: list[TableDefinition]

    @model_validator(mode="after")
    def table_names_are_unique(self) -> "DataDictionary":
        names = [table.name for table in self.tables]
        if len(names) != len(set(names)):
            raise ValueError("table names must be unique")
        return self


def load_dictionary(path: Path = DEFAULT_DICTIONARY) -> DataDictionary:
    """Load and validate a dictionary YAML file."""
    with path.open(encoding="utf-8") as source:
        raw_data = yaml.safe_load(source)
    return DataDictionary.model_validate(raw_data)
