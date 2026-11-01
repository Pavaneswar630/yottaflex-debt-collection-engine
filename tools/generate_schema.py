"""Generate the SQL schema and schema documentation from the YAML dictionary."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "schema" / "data_dictionary.yaml"
OUTPUTS = {
    ROOT / "schema" / "schema.sql": "sql",
    ROOT / "docs" / "DATA_DICTIONARY.md": "dictionary",
    ROOT / "docs" / "ER_DIAGRAM.md": "diagram",
}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
SQL_TYPE = re.compile(r"^[A-Z][A-Z0-9]*(?:\([0-9]+(?:,[0-9]+)?\))?$")
FIELD_KEYS = {
    "type",
    "required",
    "enum",
    "unit",
    "unique",
    "validation",
}


def load_schema() -> dict[str, Any]:
    with SOURCE.open(encoding="utf-8") as source_file:
        schema = yaml.safe_load(source_file)
    if not isinstance(schema, dict) or not isinstance(schema.get("tables"), list):
        raise ValueError(f"{SOURCE} must contain a mapping with a tables list")

    tables = schema["tables"]
    table_names: set[str] = set()
    for table in tables:
        name = table.get("name")
        if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
            raise ValueError(f"Invalid table name: {name!r}")
        if name in table_names:
            raise ValueError(f"Duplicate table name: {name}")
        table_names.add(name)
        fields = table.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ValueError(f"Table {name} must define fields")
        primary_keys = []
        for field_name, field in fields.items():
            if not IDENTIFIER.fullmatch(field_name):
                raise ValueError(f"Invalid field name: {name}.{field_name}")
            if not isinstance(field, dict):
                raise ValueError(f"Field metadata must be a mapping: {name}.{field_name}")
            missing = FIELD_KEYS - field.keys()
            if missing:
                raise ValueError(
                    f"{name}.{field_name} is missing required metadata: "
                    f"{', '.join(sorted(missing))}"
                )
            if not SQL_TYPE.fullmatch(field["type"]):
                raise ValueError(f"Unsupported SQL type on {name}.{field_name}")
            if not isinstance(field["required"], bool) or not isinstance(
                field["unique"], bool
            ):
                raise ValueError(f"{name}.{field_name} required/unique must be boolean")
            if not isinstance(field["enum"], list) or not isinstance(
                field["validation"], str
            ) or not isinstance(field["unit"], str) or not field["unit"]:
                raise ValueError(f"Invalid enum or validation rule on {name}.{field_name}")
            if any(not isinstance(value, str) for value in field["enum"]):
                raise ValueError(f"Enum values must be strings on {name}.{field_name}")
            if "primary_key" in field and not isinstance(field["primary_key"], bool):
                raise ValueError(f"primary_key must be boolean on {name}.{field_name}")
            if "sql_check" in field and not isinstance(field["sql_check"], str):
                raise ValueError(f"sql_check must be a string on {name}.{field_name}")
            if field.get("primary_key"):
                if not field["required"]:
                    raise ValueError(f"Primary key {name}.{field_name} must be required")
                primary_keys.append(field_name)
            reference = field.get("references")
            if reference:
                if not isinstance(reference, dict) or (
                    not IDENTIFIER.fullmatch(reference.get("table", ""))
                    or not IDENTIFIER.fullmatch(reference.get("field", ""))
                    or reference.get("on_delete")
                    not in {"RESTRICT", "CASCADE", "SET NULL"}
                ):
                    raise ValueError(f"Invalid reference on {name}.{field_name}")
                if reference["on_delete"] == "SET NULL" and field["required"]:
                    raise ValueError(
                        f"SET NULL reference must be optional: {name}.{field_name}"
                    )
        if not primary_keys:
            raise ValueError(f"Table {name} must define a primary key")

    for table in tables:
        for field_name, field in table["fields"].items():
            reference = field.get("references")
            if reference:
                target = next(
                    (item for item in tables if item["name"] == reference["table"]),
                    None,
                )
                if target is None or reference["field"] not in target["fields"]:
                    raise ValueError(f"Unknown reference on {table['name']}.{field_name}")

        for constraint in table.get("constraints", []):
            if not IDENTIFIER.fullmatch(constraint.get("name", "")):
                raise ValueError(f"Invalid constraint name in {table['name']}")
            if constraint.get("type") == "unique":
                if not constraint.get("fields") or any(
                    field_name not in table["fields"]
                    for field_name in constraint["fields"]
                ):
                    raise ValueError(f"Invalid unique constraint in {table['name']}")
            elif constraint.get("type", "check") != "check" or not constraint.get(
                "check"
            ):
                raise ValueError(f"Invalid constraint in {table['name']}")
    return schema


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def generate_sql(schema: dict[str, Any]) -> str:
    statements = [
        "-- Generated by tools/generate_schema.py; edit schema/data_dictionary.yaml.",
        "-- PostgreSQL DDL.",
        "",
    ]
    for table in schema["tables"]:
        name = table["name"]
        fields = table["fields"]
        declarations = []
        for field_name, field in fields.items():
            declaration = f"    {field_name} {field['type']}"
            if field["required"]:
                declaration += " NOT NULL"
            declarations.append(declaration)

        constraints = []
        primary_keys = [
            field_name
            for field_name, field in fields.items()
            if field.get("primary_key")
        ]
        constraints.append(
            f"    CONSTRAINT {name}_pkey PRIMARY KEY "
            f"({', '.join(primary_keys)})"
        )
        for field_name, field in fields.items():
            if field["enum"]:
                allowed_values = ", ".join(sql_literal(value) for value in field["enum"])
                constraints.append(
                    f"    CONSTRAINT {name}_{field_name}_enum "
                    f"CHECK ({field_name} IN ({allowed_values}))"
                )
            if field.get("sql_check"):
                constraints.append(
                    f"    CONSTRAINT {name}_{field_name}_check "
                    f"CHECK ({field['sql_check']})"
                )
            if field["unique"] and not field.get("primary_key"):
                constraints.append(
                    f"    CONSTRAINT {name}_{field_name}_key UNIQUE ({field_name})"
                )
            reference = field.get("references")
            if reference:
                constraints.append(
                    f"    CONSTRAINT {name}_{field_name}_fkey "
                    f"FOREIGN KEY ({field_name}) REFERENCES "
                    f"{reference['table']} ({reference['field']}) "
                    f"ON DELETE {reference['on_delete']}"
                )
        for constraint in table.get("constraints", []):
            if constraint.get("type") == "unique":
                expressions = ", ".join(constraint["fields"])
                clause = f"UNIQUE ({expressions})"
            else:
                clause = f"CHECK ({constraint['check']})"
            constraints.append(f"    CONSTRAINT {constraint['name']} {clause}")

        statements.append(
            f"CREATE TABLE {name} (\n"
            + ",\n".join(declarations + constraints)
            + "\n);"
        )
        statements.append("")
    return "\n".join(statements)


def field_key(table: dict[str, Any], field_name: str) -> str:
    field = table["fields"][field_name]
    if field.get("primary_key"):
        return "PK"
    if field.get("references"):
        reference = field["references"]
        return f"FK to {reference['table']}.{reference['field']}"
    return ""


def generate_dictionary(schema: dict[str, Any]) -> str:
    lines = [
        f"# {schema['title']} — data dictionary",
        "",
        "<!-- Generated by tools/generate_schema.py from schema/data_dictionary.yaml. -->",
        "",
        schema["description"].strip(),
        "",
        f"SQL dialect: **{schema['sql_dialect']}**. "
        "Required means `NOT NULL`; a unique field is unique across its table. "
        "Empty enum lists mean there is no enumerated-value restriction.",
        "",
        "## Entities and fields",
        "",
    ]
    for table in schema["tables"]:
        lines.extend(
            [
                f"### `{table['name']}`",
                "",
                table["description"],
                "",
                "| Field | Type | Required | Allowed values | Unit | Unique | Key / reference | Validation rule |",
                "|---|---|---:|---|---|---:|---|---|",
            ]
        )
        for field_name, field in table["fields"].items():
            allowed = ", ".join(f"`{value}`" for value in field["enum"]) or "—"
            required = "Yes" if field["required"] else "No"
            unique = "Yes" if field["unique"] else "No"
            key = field_key(table, field_name) or "—"
            validation = field["validation"].replace("|", "\\|")
            lines.append(
                f"| `{field_name}` | `{field['type']}` | {required} | {allowed} "
                f"| {field['unit']} | {unique} | {key} | {validation} |"
            )
        constraints = table.get("constraints", [])
        if constraints:
            lines.extend(["", "**Additional table constraints:**"])
            for constraint in constraints:
                if constraint.get("type") == "unique":
                    detail = f"unique across `{', '.join(constraint['fields'])}`"
                else:
                    detail = f"`CHECK ({constraint['check']})`"
                lines.append(f"- `{constraint['name']}`: {detail}.")
        lines.append("")

    lines.extend(
        [
            "## Relationships and cardinality",
            "",
            "The ER diagram is generated from the same foreign-key declarations. "
            "`||` denotes exactly one, `o|` zero or one, and `o{` zero or many. "
            "The `payment_allocation` bridge makes payment-to-installment allocation N:M.",
            "",
            "See [ER diagram](ER_DIAGRAM.md).",
            "",
            "## Cross-record validation",
            "",
            "- A collection case's optional loan must belong to its account.",
            "- A payment allocation must use the payment and installment currency, "
            "and all allocations for a payment must not exceed its posted amount.",
            "- A payment's account must own the loan that owns each allocated installment.",
            "- Arrears, days past due, installment status, risk band, and promise outcome "
            "are derived from their source records and the applicable as-of date.",
            "- Contact scheduling must honor the active effective-dated preference, "
            "the customer's local time zone, and do-not-contact restrictions.",
            "- Synthetic records must not contain real customer or payment information.",
            "",
        ]
    )
    return "\n".join(lines)


def generate_diagram(schema: dict[str, Any]) -> str:
    lines = [
        "# Entity relationship diagram",
        "",
        "<!-- Generated by tools/generate_schema.py from schema/data_dictionary.yaml. -->",
        "",
        "```mermaid",
        "erDiagram",
    ]
    for table in schema["tables"]:
        for field_name, field in table["fields"].items():
            if not field.get("references"):
                continue
            reference = field["references"]
            target = reference["table"]
            source = table["name"]
            target_cardinality = "||" if field["required"] else "o|"
            source_cardinality = "o|" if field["unique"] else "o{"
            relation = f"{target_cardinality}--{source_cardinality}"
            lines.append(f'    {target.upper()} {relation} {source.upper()} : "{field_name}"')

    lines.append("")
    mermaid_types = {
        "CHAR": "string",
        "VARCHAR": "string",
        "NUMERIC": "decimal",
        "SMALLINT": "int",
        "INTEGER": "int",
        "DATE": "date",
        "TIME": "time",
        "TIMESTAMPTZ": "datetime",
        "BOOLEAN": "boolean",
    }
    for table in schema["tables"]:
        lines.append(f"    {table['name'].upper()} {{")
        for field_name, field in table["fields"].items():
            raw_type = field["type"].split("(", maxsplit=1)[0]
            mermaid_type = mermaid_types[raw_type]
            markers = []
            if field.get("primary_key"):
                markers.append("PK")
            if field.get("references"):
                markers.append("FK")
            marker_text = f' "{",".join(markers)}"' if markers else ""
            lines.append(
                f"        {mermaid_type} {field_name}{marker_text}"
            )
        lines.append("    }")
    lines.extend(["```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if any generated file is missing or out of date",
    )
    args = parser.parse_args(argv)
    schema = load_schema()
    generated = {
        path: {
            "sql": generate_sql,
            "dictionary": generate_dictionary,
            "diagram": generate_diagram,
        }[kind](schema)
        for path, kind in OUTPUTS.items()
    }

    if args.check:
        stale = [
            path.relative_to(ROOT).as_posix()
            for path, content in generated.items()
            if not path.is_file() or path.read_text(encoding="utf-8") != content
        ]
        if stale:
            print(
                "Generated schema artifacts are missing or stale: "
                + ", ".join(stale),
                file=sys.stderr,
            )
            return 1
        print("Generated schema artifacts are up to date.")
        return 0

    for path, content in generated.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"Wrote {path.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
