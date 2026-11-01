# Requirements traceability

This matrix maps every requirement statement and list item in the supplied brief to a code, test, or documentation target. This is a scaffold: code targets identify intended ownership, not completed functionality. The YAML data dictionary, generated SQL, field reference, and ER diagram are implemented; the workflow, data generator, validation rules, and remaining feature tests are planned.

| ID | Brief requirement | Code target | Test target | Documentation target | Status |
|---|---|---|---|---|---|
| R01 | Read the brief carefully and ensure the build covers every point in it. | All mapped package modules | All mapped feature tests | This complete matrix | Matrix created; feature coverage remains planned |
| R02 | Create a requirements traceability matrix at `docs/TRACEABILITY.md`. | Not applicable | Not applicable | `docs/TRACEABILITY.md` | Complete |

## Business context and scope

| ID | Brief requirement | Code target | Test target | Documentation target | Status |
|---|---|---|---|---|---|
| B01 | Prioritize overdue accounts, schedule contact tasks, and monitor commitments without aggressive or unlawful practices. | `prioritization.py`, `contacts.py`, `reconciliation.py` | `test_prioritization.py`, `test_contact_policy.py`, `test_reconciliation.py` | README; `docs/DATA_DICTIONARY.md` | Planned |
| B02 | Build an end-to-end workflow for prioritization, compliant contact scheduling, and commitment monitoring. | `generator.py`, `prioritization.py`, `contacts.py`, `reconciliation.py` | `test_workflow.py` | README; `docs/ARCHITECTURE.md` | Planned |
| B03 | Expose key decisions and exceptions, preserve traceability, and produce measurable outputs. | `models.py`, `prioritization.py`, `validation.py` | `test_decision_traceability.py`, `test_metrics.py` | `docs/ARCHITECTURE.md`; `docs/VALIDATION.md` | Planned |
| B04 | Medium complexity requires related entities, conditional rules, an exception path, and meaningful evaluation metrics. | All domain modules | `test_workflow.py`, `test_exceptions.py`, `test_metrics.py` | `docs/ARCHITECTURE.md`; `docs/VALIDATION.md` | Planned |
| B05 | Primary actors are the customer/account holder, operations analyst, risk/compliance reviewer, and system administrator. | `models.py`, `contacts.py` | `test_actor_workflows.py` | `docs/ARCHITECTURE.md` | Planned |

## Workflow rules and entities

| ID | Brief requirement | Code target | Test target | Documentation target | Status |
|---|---|---|---|---|---|
| W01 | Generate/reference Customer, Account, Loan, Installment, and DelinquencySnapshot master data first. | `models.py`, `generator.py` | `test_generation_order.py` | `docs/DATA_DICTIONARY.md` | Planned |
| W02 | Generate dependent transaction/event records using valid parent IDs. | `generator.py`, `validation.py` | `test_foreign_keys.py` | `docs/ARCHITECTURE.md` | Planned |
| W03 | Create loan schedules and installment due dates. | `generator.py` | `test_schedule_generation.py` | `docs/DATA_DICTIONARY.md` | Planned |
| W04 | Generate payment histories. | `generator.py`, `reconciliation.py` | `test_payment_history.py` | `docs/ARCHITECTURE.md` | Planned |
| W05 | Derive days-past-due and arrears. | `generator.py`, `models.py` | `test_delinquency_calculations.py` | `docs/DATA_DICTIONARY.md` | Planned |
| W06 | Create contact preferences and permissible contact windows. | `contacts.py`, `generator.py` | `test_contact_policy.py` | `docs/DATA_DICTIONARY.md` | Planned |
| W07 | Score cases from balance, age, and risk. | `prioritization.py` | `test_prioritization.py` | `docs/ARCHITECTURE.md` | Planned |
| W08 | Record contact outcomes and promises. | `contacts.py`, `models.py` | `test_contact_events.py`, `test_promise_lifecycle.py` | `docs/DATA_DICTIONARY.md` | Planned |
| W09 | Reconcile payments to commitments. | `reconciliation.py` | `test_reconciliation.py` | `docs/VALIDATION.md` | Planned |
| W10 | Persist state changes as explicit records/events where relevant; do not overwrite history. | `models.py`, `contacts.py`, `reconciliation.py` | `test_event_history.py` | `docs/ARCHITECTURE.md` | Planned |
| W11 | Core entities are Customer, Account, Loan, Installment, DelinquencySnapshot, ContactPreference, ContactAttempt, PromiseToPay, Payment, and CollectionCase. | `schema/data_dictionary.yaml` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md` | Schema defined; domain implementation planned |
| W12 | Define a primary key for every entity and foreign keys for every relationship. | `schema/data_dictionary.yaml`, `tools/generate_schema.py` | `test_schema_generation.py` | `schema/schema.sql` | Schema and generated constraints complete |
| W13 | Document cardinality (1:1, 1:N, N:M), optional relationships, effective dates, and lifecycle states. | `schema/data_dictionary.yaml` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md`, `docs/ER_DIAGRAM.md` | Schema documentation complete; lifecycle implementation planned |
| W14 | Use bridge tables for many-to-many relationships; retain event history for state changes; validate all joins. | `schema/data_dictionary.yaml`, `tools/generate_schema.py` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md`, `docs/ER_DIAGRAM.md` | Allocation bridge defined; event-history and join validation planned |
| W15 | Deliberate anomaly cases retain an issue_type/ground_truth label instead of silently corrupting unrelated rows. | `generator.py`, `models.py`, `validation.py` | `test_labeled_anomalies.py` | `docs/VALIDATION.md` | Planned |

## IDs, generation, and data coverage

| ID | Brief requirement | Code target | Test target | Documentation target | Status |
|---|---|---|---|---|---|
| G01 | Use the LOAN-2026-000001 ID form. | `generator.py` | `test_id_conventions.py` | `docs/DATA_DICTIONARY.md` | Planned |
| G02 | Use INS-<loan-id>-001 installment IDs. | `generator.py` | `test_id_conventions.py` | `docs/DATA_DICTIONARY.md` | Planned |
| G03 | Use COL-2026-000001 collection-case IDs. | `generator.py` | `test_id_conventions.py` | `docs/DATA_DICTIONARY.md` | Planned |
| G04 | Use CTP-<case-id>-001 contact-attempt IDs. | `generator.py` | `test_id_conventions.py` | `docs/DATA_DICTIONARY.md` | Planned |
| G05 | Use PMT-2026-000001 payment IDs. | `generator.py` | `test_id_conventions.py` | `docs/DATA_DICTIONARY.md` | Planned |
| G06 | Write a data dictionary covering all ten named entities. | `schema/data_dictionary.yaml`, `tools/generate_schema.py` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md` | Complete; includes payment allocation bridge |
| G07 | Specify every field's type, required/optional status, allowed values, units, uniqueness, and validation rule. | `schema/data_dictionary.yaml`, `tools/generate_schema.py` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md` | Complete |
| G08 | Create parent/master tables before child and event tables. | `generator.py` | `test_generation_order.py` | `docs/ARCHITECTURE.md` | Planned |
| G09 | Keep counters zero-padded, IDs immutable, and referenced IDs exactly consistent across files. | `generator.py`, `validation.py` | `test_id_conventions.py`, `test_foreign_keys.py` | `docs/VALIDATION.md` | Planned |
| G10 | Generate 10,000 loans and 30,000 installments across 12 months. | `generator.py` | `test_full_scale_profile.py` | README; `docs/GENERATION.md` | Planned |
| G11 | Include partial payments, missed promises, disputes, hardship flags, paid-off accounts, and contact restrictions. | `generator.py` | `test_coverage_profile.py` | `docs/GENERATION.md` | Planned |
| G12 | Use fixed seed 20261022 (or another documented fixed seed). | `generator.py` | `test_reproducibility.py` | README; `docs/GENERATION.md` | Planned |
| G13 | Parameterize scale so starter and full datasets use the same generator. | `generator.py`, `cli.py` | `test_scale_profiles.py` | README; `docs/GENERATION.md` | Planned |
| G14 | Generate valid baseline records before injecting labelled edge cases. | `generator.py` | `test_labeled_anomalies.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` | Planned |
| G15 | Include the paid account remaining in collection case. | `generator.py`, `validation.py` | `test_edge_cases.py` | `docs/VALIDATION.md` | Planned |
| G16 | Include contact outside the allowed window case. | `generator.py`, `contacts.py`, `validation.py` | `test_edge_cases.py`, `test_contact_policy.py` | `docs/VALIDATION.md` | Planned |
| G17 | Include payment allocated to the wrong installment case. | `generator.py`, `reconciliation.py`, `validation.py` | `test_edge_cases.py`, `test_reconciliation.py` | `docs/VALIDATION.md` | Planned |
| G18 | Include promise amount exceeding arrears case. | `generator.py`, `reconciliation.py`, `validation.py` | `test_edge_cases.py`, `test_promise_lifecycle.py` | `docs/VALIDATION.md` | Planned |
| G19 | Include disputed debt treated as confirmed case. | `generator.py`, `prioritization.py`, `validation.py` | `test_edge_cases.py` | `docs/VALIDATION.md` | Planned |
| G20 | Calculate totals, balances, scores, statuses, and dates from source records rather than independently generating them. | `generator.py`, `prioritization.py`, `reconciliation.py` | `test_derived_values.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` | Planned |
| G21 | Export separate ground_truth.csv/json for known anomalies, expected decisions, or labels. | `generator.py` | `test_ground_truth_separation.py` | `docs/GENERATION.md` | Planned |
| G22 | Never leak ground-truth labels into input features. | `generator.py`, `validation.py` | `test_ground_truth_separation.py` | `docs/VALIDATION.md` | Planned |
| G23 | Keep the generator and its fixed seed as the source of reproducible synthetic records. | `generator.py` | `test_reproducibility.py` | `docs/GENERATION.md` | Planned |

## Validation and evaluation

| ID | Brief requirement | Code target | Test target | Documentation target | Status |
|---|---|---|---|---|---|
| V01 | Validate primary-key uniqueness. | `validation.py` | `test_primary_keys.py` | `docs/VALIDATION.md` | Planned |
| V02 | Validate foreign-key integrity. | `validation.py` | `test_foreign_keys.py` | `docs/VALIDATION.md` | Planned |
| V03 | Validate allowed enums. | `validation.py` | `test_allowed_values.py` | `docs/VALIDATION.md` | Planned |
| V04 | Validate date ordering. | `validation.py` | `test_date_ordering.py` | `docs/VALIDATION.md` | Planned |
| V05 | Validate arithmetic reconciliation. | `validation.py`, `reconciliation.py` | `test_reconciliation.py` | `docs/VALIDATION.md` | Planned |
| V06 | Validate lifecycle transitions. | `validation.py`, `models.py` | `test_lifecycle_transitions.py` | `docs/VALIDATION.md` | Planned |
| V07 | Validate duplicate checks. | `validation.py` | `test_duplicates.py` | `docs/VALIDATION.md` | Planned |
| V08 | Ensure arrears calculations reconcile. | `reconciliation.py`, `validation.py` | `test_delinquency_calculations.py` | `docs/VALIDATION.md` | Planned |
| V09 | Make prioritization explainable. | `prioritization.py` | `test_prioritization.py` | `docs/ARCHITECTURE.md` | Planned |
| V10 | Enforce contact restrictions. | `contacts.py`, `validation.py` | `test_contact_policy.py` | `docs/VALIDATION.md` | Planned |
| V11 | Make promise outcomes match subsequent payments. | `reconciliation.py` | `test_reconciliation.py`, `test_promise_lifecycle.py` | `docs/VALIDATION.md` | Planned |
| V12 | Evaluate realistic distributions and meaningful variation. | `generator.py`, `validation.py` | `test_distribution_metrics.py` | `docs/VALIDATION.md` | Planned |
| V13 | Evaluate consistent IDs and valid joins. | `generator.py`, `validation.py` | `test_id_conventions.py`, `test_foreign_keys.py` | `docs/VALIDATION.md` | Planned |
| V14 | Evaluate dependency/lifecycle consistency across entities. | `models.py`, `validation.py` | `test_lifecycle_transitions.py`, `test_relationships.py` | `docs/VALIDATION.md` | Planned |
| V15 | Evaluate correct derived values and reconciliation. | `generator.py`, `reconciliation.py`, `validation.py` | `test_derived_values.py`, `test_reconciliation.py` | `docs/VALIDATION.md` | Planned |
| V16 | Cover normal, boundary, failure, and exception scenarios. | `generator.py`, `validation.py` | `test_coverage_profile.py`, `test_edge_cases.py` | `docs/VALIDATION.md` | Planned |
| V17 | Keep ground truth separate. | `generator.py`, `validation.py` | `test_ground_truth_separation.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` | Planned |
| V18 | Demonstrate fixed-seed reproducibility. | `generator.py` | `test_reproducibility.py` | `docs/GENERATION.md` | Planned |
| V19 | Provide documentation, fixed seed, source manifest, and validation summary. | `generator.py`, `validation.py` | `test_export_manifest.py` | README; `docs/GENERATION.md`; `docs/VALIDATION.md` | Planned |
| V20 | Regenerate twice with the same seed and compare row counts and checksums. | `generator.py`, `validation.py` | `test_reproducibility.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` | Planned |

## Exports, provenance, and submission

| ID | Brief requirement | Code target | Test target | Documentation target | Status |
|---|---|---|---|---|---|
| P01 | Export CSV, JSON, and SQL seed data. | `generator.py` | `test_export_formats.py` | `docs/GENERATION.md` | Planned |
| P02 | Include README, schema/data dictionary, generator command, fixed seed, source manifest, and validation summary. | `cli.py`, `generator.py`, `validation.py` | `test_export_manifest.py` | README; `docs/DATA_DICTIONARY.md`; `docs/GENERATION.md`; `docs/VALIDATION.md` | README and this matrix exist; remaining docs planned |
| P03 | External data is optional. | `generator.py` | `test_synthetic_only_mode.py` | README; `docs/GENERATION.md` | Planned |
| P04 | For any external source, record URL, dataset/version, retrieval date, license/terms, attribution, transformations, and discarded fields. | `generator.py` | `test_source_manifest.py` | `docs/GENERATION.md` | Planned; no external data currently used |
| P05 | Use only legally accessible and redistributable data; do not bypass access controls or collect confidential/personal information. | `generator.py` | `test_synthetic_only_mode.py`, `test_source_manifest.py` | README; `docs/GENERATION.md` | No external or personal data included |
| P06 | If licensing or suitability is unclear, use synthetic data and cite public reference data only for schema inspiration. | `generator.py` | `test_synthetic_only_mode.py` | `docs/GENERATION.md` | Planned |
| P07 | Push the code to a public GitHub repository before submission. | Repository setup/release process | Not applicable | README | Not performed by this local scaffold |
| P08 | Add a README explaining how to run it. | `cli.py` | `test_cli.py` | README | Scaffold usage instructions added; data-generation command awaits implementation |
| P09 | Include any tests requested by the problem. | All domain modules | `tests/` | README; this matrix | Smoke test exists; domain tests are planned |
| P10 | Create the repository, `pyproject.toml`, Makefile, and CI-less skeleton. | Project root and `src/yottaflex_debt_collection/` | `test_cli.py` | README; this matrix | Scaffold created; no CI workflow add |
