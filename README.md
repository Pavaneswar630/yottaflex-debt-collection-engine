# Yottaflex Debt Collection Engine

A Python project scaffold for a synthetic, explainable debt-collection workflow. The intended solution prioritizes overdue accounts, schedules compliant contact tasks, and monitors payment commitments while preserving event history and exception traceability.

## Status

This repository contains a CI-less project scaffold, a YAML source-of-truth data dictionary, hand-maintained PostgreSQL DDL, generated schema documentation, policy rules, and deterministic ID/RNG/money foundations. The end-to-end workflow, data generator, and full validation suite are not implemented yet; see [docs/TRACEABILITY.md](docs/TRACEABILITY.md) for implementation status.

## Requirements

- Python 3.10 or newer
- GNU Make to use the convenience targets (or run the Python commands directly)

## Setup and run

```shell
python -m venv .venv
# Activate the virtual environment using the command for your shell.
python -m pip install -e ".[dev]"
python -m yottaflex_debt_collection --help
```

The current command is a scaffold entry point and does not generate data yet.

## Development

```shell
make setup
make test
make validate
make schema
```

`make schema` regenerates `docs/DATA_DICTIONARY.md` from `schema/data_dictionary.yaml`. `schema/schema.sql` and `docs/ER.md` are hand-maintained; keep them aligned with the YAML dictionary. To verify generated documentation without modifying it, run `python tools/generate_schema.py --check`.

`make data`, `make data-starter`, `make repro`, `make api`, `make ui`, `make demo`, and `make eval-ai` are explicit stubs until those features are implemented. The as-of and generation dates are both fixed to `2026-10-31`; the seed is `20261022`.

The fixed-seed, parameterized generator and CSV/JSON/SQL exports described in the brief are planned work, not available commands in this scaffold. No external or personal data is included. This project has no CI configuration by design.

The generation foundations use seed `20261022`, fixed dates, named NumPy child streams, sequential ID factories, and integer cents in code and schema. See [docs/GENERATION.md](docs/GENERATION.md); the end-to-end generator is not yet implemented.

## Project layout

- `src/yottaflex_debt_collection/`: package entry point and planned domain modules for models, generation, prioritization, contact policy, payment reconciliation, and validation.
- `tests/`: pytest coverage for IDs, the data dictionary, policy, Make targets, and CLI foundations.
- `schema/data_dictionary.yaml`: canonical entity, field, validation, and relationship definitions.
- `config/policy.yaml`: ID-addressable example rules for contact limits, disputes, hardship, cease-contact requests, paid-off loans, scoring, payment allocation, and reconciliation. Review with compliance counsel before production use.
- `schema/schema.sql`: hand-maintained PostgreSQL DDL with constraints and FK indexes.
- `docs/DATA_DICTIONARY.md`: generated field reference.
- `docs/ER.md`: Mermaid relationship diagram and explicit cardinality/optionality table.
- `docs/ASSUMPTIONS.md`: tracked assumptions and the unresolved ContactAttempt ID question.
- `tools/generate_schema.py`: generator and staleness check for the schema artifacts.
- `docs/TRACEABILITY.md`: maps each requirement in the brief to its planned code, test, or documentation target and records implementation status.
- `docs/GENERATION.md`: documents deterministic seed, named RNG streams, ID helpers, integer-cent money, and fixed as-of date.
- `src/yottaflex_debt_collection/schema_loader.py`: Pydantic loader for the YAML data dictionary.
