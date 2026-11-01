# Yottaflex Debt Collection Engine

A Python project scaffold for a synthetic, explainable debt-collection workflow. The intended solution prioritizes overdue accounts, schedules compliant contact tasks, and monitors payment commitments while preserving event history and exception traceability.

## Status

This repository contains a YAML source-of-truth data dictionary, hand-maintained PostgreSQL DDL, generated schema documentation, policy rules, deterministic ID/RNG/money foundations, and a reproducible synthetic CSV generator. The broader collection workflow is still under development; see [docs/TRACEABILITY.md](docs/TRACEABILITY.md) for implementation status.

## Requirements

- Python 3.10 or newer
- GNU Make to use the convenience targets (or run the Python commands directly)

## Setup and run

```shell
python -m venv .venv
# Activate the virtual environment using the command for your shell.
python -m pip install -e ".[dev]"
python -m yottaflex_debt_collection --help
python -m yottaflex_debt_collection --loans 10000 --seed 20261022
```

The generator writes entity CSVs under `data/` and isolated labels to `ground_truth/latent_segments.csv`. Use `--output-dir PATH` to write beneath another dataset root. `--loans` defaults to 10,000 and `--seed` defaults to 20261022.

## Development

```shell
make setup
make test
make validate
make schema
```

`make schema` regenerates `docs/DATA_DICTIONARY.md` from `schema/data_dictionary.yaml`. `schema/schema.sql` and `docs/ER.md` are hand-maintained; keep them aligned with the YAML dictionary. To verify generated documentation without modifying it, run `python tools/generate_schema.py --check`.

`make data` creates the full 10,000-loan dataset; `make data-starter` creates a 100-loan sample; `make repro` checks repeat-generation checksums. The API, UI, demo, and AI-evaluation targets remain stubs. The as-of and generation dates are fixed to `2026-10-31`.

The generator creates synthetic customer risk bands and timezones, accounts, loans, quarterly installment schedules, effective-dated contact preferences, optional dispute and hardship records, payments, and oldest-first payment allocations. Any unapplied payment balance is recorded explicitly. Latent behavior labels use the requested approximate proportions and are kept outside the input CSVs. No external or personal data is included. This project has no CI configuration by design.

The generation foundations use a configurable seed, fixed dates, named NumPy child streams, sequential ID factories, and integer cents in code and schema. See [docs/GENERATION.md](docs/GENERATION.md) for output details and validation.

## Project layout

- `src/yottaflex_debt_collection/`: package CLI, synthetic generator, deterministic foundations, and planned prioritization, contact-policy, and promise-reconciliation modules.
- `tests/`: pytest coverage for IDs, the data dictionary, policy, Make targets, CLI, and generator reproducibility.
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
