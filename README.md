# Yottaflex Debt Collection Engine

A Python project scaffold for a synthetic, explainable debt-collection workflow. The intended solution prioritizes overdue accounts, schedules compliant contact tasks, and monitors payment commitments while preserving event history and exception traceability.

## Status

This repository contains a CI-less project scaffold, a YAML source-of-truth data dictionary, and generated PostgreSQL DDL and schema documentation. The workflow, data generator, validation rules, and full test suite are not implemented yet; see [docs/TRACEABILITY.md](docs/TRACEABILITY.md) for implementation status.

## Requirements

- Python 3.10 or newer
- GNU Make to use the convenience targets (or run the Python commands directly)

## Setup and run

```shell
python -m venv .venv
# Activate the virtual environment using the command for your shell.
python -m pip install -e .
python -m yottaflex_debt_collection --help
```

The current command is a scaffold entry point and does not generate data yet.

## Development

```shell
make test
make run
make schema
```

`make schema` regenerates `schema/schema.sql`, `docs/DATA_DICTIONARY.md`, and `docs/ER_DIAGRAM.md` from `schema/data_dictionary.yaml`. To verify generated files without modifying them, run `python tools/generate_schema.py --check`.

Equivalent direct commands are `python -m unittest discover -s tests -v` and `python -m yottaflex_debt_collection --help`.

The fixed-seed, parameterized generator and CSV/JSON/SQL exports described in the brief are planned work, not available commands in this scaffold. No external or personal data is included. This project has no CI configuration by design.

## Project layout

- `src/yottaflex_debt_collection/`: package entry point and planned domain modules for models, generation, prioritization, contact policy, payment reconciliation, and validation.
- `tests/`: local tests for the CLI scaffold, schema generation, and policy configuration.
- `schema/data_dictionary.yaml`: canonical entity, field, validation, and relationship definitions.
- `config/policy.yaml`: configurable example defaults for contact windows and attempt limits, payment allocation, case scoring, DPD buckets, and dispute/hardship holds. Review against applicable requirements before production use.
- `schema/schema.sql`: generated PostgreSQL table definitions.
- `docs/DATA_DICTIONARY.md`, `docs/ER_DIAGRAM.md`: generated field reference and Mermaid ER diagram.
- `tools/generate_schema.py`: generator and staleness check for the schema artifacts.
- `docs/TRACEABILITY.md`: maps each requirement in the brief to its planned code, test, or documentation target and records implementation status.
