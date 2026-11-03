# SQLite database and read-only API

## Load the dataset

Generate full exports, then load them into SQLite:

```powershell
make data
make db-load
```

The loader uses `schema/sqlite_schema.sql`, imports CSVs in dependency order, enables `PRAGMA foreign_keys=ON`, and runs `PRAGMA foreign_key_check` before replacing the output database. It refuses to overwrite an existing database unless `--overwrite` is passed. The optional latent-segment table is imported from `ground_truth/full/latent_segments.csv` solely for the promise-by-segment analytics view; API responses do not return row-level latent labels.

For custom locations:

```powershell
python -m yottaflex_debt_collection.database `
  --data-dir data/full `
  --ground-truth-dir ground_truth/full `
  --db data/full/collection.sqlite `
  --overwrite
```

## Analytics views

| View | Output |
|---|---|
| `latest_snapshot` | One latest snapshot per loan, preferring `as_of`, then `case_open`, then `month_end` on a shared date via `ROW_NUMBER()`. |
| `roll_rates` | Month-end delinquency bucket transitions per loan using `LAG()`, aggregated by source and destination bucket. |
| `promise_kept_by_segment` | Promise count, kept count, and kept rate by isolated latent behavior segment. |
| `cure_rate` | Delinquent loans with a case-open snapshot and their latest snapshot; a cure is a positive initial DPD and zero latest DPD. |
| `violations_by_rule` | Counts blocked/review/closed decision outcomes by rule and decision type. |
| `priority_queue` | Open cases with stored score components and latest DPD/arrears, ordered by score in the API. |

## API endpoints

Start the server with `make api`. All endpoints are read-only. For the React UI, start `make ui` in a second terminal and open `http://127.0.0.1:5173`; Vite proxies `/api` requests to the local API.

| Method and path | Description |
|---|---|
| `GET /health` | SQLite quick check and foreign-key setting. |
| `GET /queue?limit=100&offset=0` | Open priority queue, highest score first. |
| `GET /cases/{id}` | Case, account/customer risk band, loan and latest delinquency snapshot. |
| `GET /cases/{id}/timeline` | Case state events, contact attempts, promises, and promise-payment reconciliations in time order. |
| `GET /decisions?case_id=...&limit=100&offset=0` | Decision log, optionally filtered by case. |
| `GET /exceptions?issue_type=...&limit=100&offset=0` | Three input-only blind detector results. |
| `GET /metrics` | Analytics-view outputs and open queue count. |
| `GET /admin/policy` | Current YAML policy configuration. |
| `GET /admin/validation` | Integrity validation result for the loaded CSV directory. |
| `GET /admin/manifest` | Dataset seed, row counts, source statement, and checksums. |
| `POST /copilot/chat` | Grounded policy answer with citations and optional fixed read-only case tools. |
| `POST /copilot/check-outreach` | Deterministic check for threats, third-party disclosures, abusive language, and the dispute notice. |

Configure the input paths with `YOTTAFLEX_DATA_DIR`, `YOTTAFLEX_DB_PATH`, and `YOTTAFLEX_GROUND_TRUTH_DIR` environment variables. The copilot endpoints do not write to the collection database or schedule/send contact. Admin endpoints expose read-only configuration/validation information; no write, policy-edit, or customer-contact endpoint is provided. See [docs/AI.md](AI.md) for provider opt-in, guardrails, and logging.

## Verification

`tests/test_database_api.py` loads a generated dataset into SQLite, verifies FK enforcement, compares all six view outputs against independent pandas recomputations, and exercises the API including suppressed cases and blocked contact history.

The UI API path types are generated from the FastAPI OpenAPI schema. After changing API routes, refresh them with `make api-types`.
