# Source and provenance manifest

## Data sources

| Dataset or input | Source/version | Retrieved | License/terms | Attribution |
|---|---|---|---|---|
| Generated customers, accounts, loans, installments, snapshots, preferences, events, cases, payments, and labels | Generated locally by this repository; seed `20261022` by default; generator implementation in `src/yottaflex_debt_collection/generator.py` | Not applicable | No third-party dataset license applies; generated output has no separate data license in this repository | None |
| Collection policy configuration | Synthetic example rules in `config/policy.yaml` | Not applicable | Educational example; not a legal authority or compliance certification | None |
| Schema and terminology inspiration | User-provided project requirements and repository-authored schema | Not applicable | No external reference dataset copied | None |

## Transformations and exclusions

- All records and outcomes are synthetic and deterministic for a fixed seed and arguments.
- The generator derives transaction/event records from valid parent IDs and documented business rules.
- Labeled edge cases are injected after baseline generation; labels are exported only under `ground_truth/` and are excluded from model-input exports.
- No external fields are ingested, and no real customer, account, payment, or contact information is collected.
- Dataset manifests in generated output directories record the seed, configuration, row counts, source statement, and checksums for exported files.

## Lawful-use statement

No public or private external data is used. Do not replace synthetic inputs with customer data without approved legal basis, privacy review, security controls, and authorization to process and redistribute it. This project is not legal advice and does not establish compliance with any jurisdiction's collection laws.
