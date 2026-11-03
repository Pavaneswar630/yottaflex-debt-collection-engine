# Yottaflex Debt Collection Engine

This project demonstrates a reproducible, synthetic workflow for prioritizing overdue accounts, applying contact restrictions, recording promises, reconciling payments, and surfacing exceptions. It does not send communications or make legally binding decisions.

## Actors and screens

| Actor | Screen or interface | What they can do |
|---|---|---|
| Customer/account holder | No direct customer portal is included | The synthetic account holder is represented in case data; no real outreach or payment action is performed. |
| Operations analyst | Priority queue and case detail | Review ranked open cases, transparent score components, reason codes, event timelines, and policy-grounded explanations. |
| Risk/compliance reviewer | Compliance and metrics | Inspect detector findings, blocked/suppressed decisions, promise outcomes, cure rates, and rule-level counts. |
| System administrator | Administration screen and read-only API | Review health, validation output, dataset manifest, and active policy configuration. |

## Workflow

1. Generate deterministic synthetic master and dependent records using the fixed seed.
2. Derive delinquency, arrears, scores, permitted contact windows, decisions, and promise outcomes from those records and documented rules.
3. Keep anomaly labels separate from input data and report violations with their rule IDs.
4. Load exports into foreign-key-enforced SQLite for read-only analytics and API access.
5. Review the dashboard or run the demo to see queue priorities, a suppressed case, and a blocked-contact decision.

## Key safeguards

- The copilot explains source policy and recorded facts; it cannot score, schedule, suppress, or contact.
- The contact scheduler records allowed, blocked, and suppressed decisions with rule IDs.
- Contact preferences, local-time windows, weekly caps, disputes, hardship, and paid-off states govern scheduling.
- Known anomaly truth remains isolated from detector input features.
- All data is synthetic. Review [SOURCE_MANIFEST.md](./SOURCE_MANIFEST.md), [DESIGN.md](./docs/DESIGN.md), and [ASSUMPTIONS.md](./docs/ASSUMPTIONS.md) before extending the demonstration.

## Measurable outputs

- Per-rule precision, recall, and F1 for the blind detectors.
- Promise kept/partial/broken counts, cure rates, roll rates, and blocked/suppressed decisions.
- Reproducible row counts and SHA-256 checksums for exported files.

These are synthetic evaluation measures, not claims about real-world collection performance.
