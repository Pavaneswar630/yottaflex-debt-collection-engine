# Yottaflex Debt Collection Engine

A synthetic, reproducible demonstration for prioritizing overdue accounts, applying contact restrictions, recording promises, reconciling payments, and exposing exceptions. It does not send communications or make legally binding decisions.

## Quickstart (Docker)

Requirements: Docker Desktop with Compose. The first run generates the default 10,000-loan dataset and loads SQLite; initialization may take a few minutes.

```powershell
docker compose up --build -d
docker compose logs -f api ui
docker compose down
```

While the services are running, open **http://127.0.0.1:8080**. The API health endpoint is at **http://127.0.0.1:8000/health**. Compose stores synthetic data, ground-truth labels, and copilot logs in named volumes.

For a faster smoke run, set `$env:YOTTAFLEX_LOANS = "100"` before `docker compose up`. Resetting volumes permanently deletes generated state; use `docker compose down -v` only when you intend to regenerate it.

## Local setup and generation

Requirements: Python 3.10+, Node.js 22+ for the UI, and GNU Make for convenience targets. On Windows, `tzdata` is installed as a project dependency so Python can resolve IANA time zones.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ai]"
.\.venv\Scripts\python.exe -m yottaflex_debt_collection --dataset full --loans 10000 --seed 20261022
```

The generator writes entity CSVs, model-input-only `dataset.json`, SQL seed data, and a checksummed manifest to `data/full/`. Edge-case labels and expected decisions are kept separately in `ground_truth/full/`. The default seed is `20261022`; dates are fixed to `2026-10-31`. Regenerate the starter dataset with:

```powershell
.\.venv\Scripts\python.exe -m yottaflex_debt_collection --dataset starter --loans 100 --seed 20261022 --anomaly-rows 50
```

`--output-dir PATH` changes the output root. Dataset exports are ignored by Git and can be regenerated with the same arguments.

## Local development and verification

```powershell
make setup
make test
make validate
make schema
```

On Windows without GNU Make, run the underlying commands directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m yottaflex_debt_collection.integrity --data-dir data/full
.\.venv\Scripts\python.exe tools\generate_schema.py --check
```

Use `make repro` to generate the full dataset twice, compare every exported SHA-256 checksum and row count, and write the proof to [docs/validation_summary.md](docs/validation_summary.md). Use `make eval-ai` to evaluate 18 fixed retrieval questions; it uses the local deterministic fallback and writes an ignored JSONL report. Equivalent commands are `.\.venv\Scripts\python.exe tools\repro.py --dataset full --loans 10000 --seed 20261022 --anomaly-rows 50 --report docs\validation_summary.md` and `.\.venv\Scripts\python.exe tools\eval_ai.py --questions tests\ai_golden_questions.json --log reports\ai_evaluation.jsonl`.

Run `npm --prefix ui ci` once, then `make ui-build` to type-check/build the React UI. For local API/UI development, load SQLite with `make db-load`, run `make api` and `make ui` in separate terminals, and open **http://127.0.0.1:5173**. The UI proxies `/api` requests to the local read-only API. Run `make demo` after loading the database to print top cases, a suppressed case, and a blocked-contact decision without scheduling or sending contact.

## Workflow and outputs

The generator creates synthetic customers, accounts, loans, quarterly installment schedules, effective-dated preferences, disputes, hardship requests, payments, payment allocations, delinquency snapshots, collection cases, decisions, contact attempts, promises, reconciliations, and state events. Derived arrears, days-past-due, score components, statuses, and outcomes are calculated from source records.

The pipeline validates primary keys, foreign keys, enums, dates, arithmetic, lifecycles, and duplicates. It injects labeled boundary and failure cases only after creating a clean baseline, recomputes affected derived data, and checks that every changed ID is represented in ground truth. Blind detectors do not use the labels; evaluation reports precision, recall, and F1. See [docs/GENERATION.md](docs/GENERATION.md), [docs/coverage_report.md](docs/coverage_report.md), and [docs/TRACEABILITY.md](docs/TRACEABILITY.md).

## User interfaces and limitations

The UI includes:

- **Priority queue:** ranked open cases, score tiers, and reason codes.
- **Case details:** score breakdown, recorded timeline, and policy copilot with citations.
- **Compliance & metrics:** detector findings, blocked/suppressed decisions, promise outcomes, and cure rates.
- **Administration:** health, validation, manifest, and policy views.

Actor/screen mapping is in [SUMMARY.md](SUMMARY.md); architecture and boundaries are in [docs/DESIGN.md](docs/DESIGN.md). The copilot uses deterministic local templates unless an API key is explicitly configured. It is read-only and cannot make scoring, scheduling, suppression, or contact decisions.

All records are synthetic; no external or personal data is used. Example rules are not legal advice or a compliance certification. The project does not include customer authentication, real payment processing, agent authorization, or outbound messaging. Do not use real customer data or operationalize the example policy without required privacy, security, legal, and compliance review. See [SOURCE_MANIFEST.md](SOURCE_MANIFEST.md), [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md), and [docs/AI.md](docs/AI.md).

## Repository map

- `src/yottaflex_debt_collection/`: deterministic generator, validation, SQLite loader, read-only API, and policy copilot.
- `schema/data_dictionary.yaml`: canonical entity and field definitions; `schema/schema.sql` and `schema/sqlite_schema.sql`: database schemas.
- `config/policy.yaml`: ID-addressable illustrative policy rules.
- `ui/`: React/TypeScript dashboard and generated OpenAPI types.
- `tests/`: generation, validation, detector, SQL/API, UI contract, copilot, and evaluation tests.
- `tools/`: reproducibility, schema generation, evaluation, and demo commands.
- `docs/`: data dictionary, entity relationships, assumptions, design, coverage, provenance/traceability, and validation evidence.

No CI workflow is configured. The release tag and Git operations are intentionally left to the repository owner after local review.
