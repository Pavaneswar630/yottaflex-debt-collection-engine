# System design

## Scope and trust boundaries

The application is a synthetic workflow demonstration. The generator and policy engine create and record operational decisions; the API exposes those records read-only; the React UI presents them. The copilot can retrieve policy text and invoke only fixed read-only data tools. It cannot change source records, calculate the official score, authorize contact, or schedule/send a message.

```text
Fixed seed + policy configuration
              |
              v
Synthetic generator --> CSV / JSON / SQL + isolated ground truth
              |                              |
              +--> integrity checks          +--> detector evaluation only
              |
              v
      FK-enforced SQLite --> Read-only FastAPI --> React dashboard
                                   |
                                   +--> BM25 policy/docs + copilot tools
```

## Data and decision flow

1. Create parent records before dependent events and validate every referenced ID.
2. Derive schedules, payment allocations, arrears, DPD, preferences, and case scores from source records.
3. Apply contact limits and suppression rules before scheduling. Persist each outcome with its rule ID.
4. Record contact/promise lifecycle events and reconcile commitments against eligible payments.
5. Inject labeled edge cases into a clean baseline, recompute derived layers, and verify changed IDs against labels.
6. Export reproducibly; load operational records into SQLite with foreign-key enforcement. The labels are held in a separate directory and are only used for offline evaluation or aggregate segment metrics.

The scoring formula and weights, contact policy, lifecycle rules, and promise reconciliation tolerance are configured in `config/policy.yaml`. See [GENERATION.md](./GENERATION.md), [ER.md](./ER.md), and [API.md](./API.md) for implementation details.

## Runtime components

- **Generator:** deterministic seeded outputs, explicit anomaly labels, validation, and checksums.
- **SQLite loader and analytics:** transactionally loads CSVs, enforces foreign keys, and creates window-function views.
- **FastAPI:** read-only case, event, decision, exception, metrics, and administration endpoints.
- **React UI:** queue, case detail, compliance/metrics, and administration screens with loading/error states.
- **Policy copilot:** BM25 retrieval with citations, optional provider integration, fixed read-only tools, deterministic outreach guardrails, and interaction logging.
- **Docker Compose:** builds the API and UI from a multi-stage Dockerfile, persists generated data in named volumes, and waits for API health before serving the UI.

## Limitations

- All generated customers and behavior are synthetic; distributions do not establish production effectiveness.
- Policy examples require jurisdiction-specific review by qualified legal/compliance staff.
- There is no customer login, payment processing, agent authorization system, or outbound communication integration.
- The copilot evaluation measures deterministic retrieval/template behavior, not an external model's legal or factual reliability.
- Ground-truth labels must never be exposed to a production scoring or detection feature.
