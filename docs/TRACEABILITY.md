# Requirements traceability

This matrix maps every requirement statement and list item in the supplied brief to a code, test, or documentation target. The schema, policy, ID/RNG foundations, and checklist artifacts are implemented. The end-to-end workflow and synthetic data generation remain planned. Each row preserves implementation status in the Doc column.

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| **R01** Read the brief carefully and ensure the build covers every point in it. | All mapped package modules | All mapped feature tests | This complete matrix ; status: Matrix created; feature coverage remains planned |
| **R02** Create a requirements traceability matrix at `docs/TRACEABILITY.md`. | Not applicable | Not applicable | `docs/TRACEABILITY.md` ; status: Complete |

## Deterministic generation requirements

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| **D01** Use zero-padded ID counters and exact schema ID formats. | `ids.py`, `generator.py` | `test_ids.py`, `test_foundations.py::IdFactoryTests` | `docs/GENERATION.md` ; status: Helper functions and factory implemented; generator integration planned |
| **D02** Issued IDs are immutable and deterministic for the same arguments. | `ids.py` | `test_ids.py` | `docs/GENERATION.md` ; status: Implemented as immutable strings |
| **D03** Use one fixed seed and named NumPy child RNG streams per entity. | `settings.py`, `rng.py`, `generator.py` | `test_foundations.py::EntityRandomStreamsTests` | `docs/GENERATION.md` ; status: Singleton named child streams implemented; generator integration planned |
| **D04** Represent money as integer cents. | `money.py`, `schema/data_dictionary.yaml`, `models.py`, `reconciliation.py` | `test_foundations.py::MoneyTests`, `test_schema_generation.py` | `docs/GENERATION.md`, `docs/DATA_DICTIONARY.md` ; status: Integer-cent conversion and BIGINT schema fields implemented; domain integration planned |
| **D05** Use a fixed as-of date and never derive dates from `now()`. | `settings.py`, `generator.py` | `test_foundations.py::ReproducibilityDefaultsTests` | `docs/GENERATION.md` ; status: Fixed date implemented; generator integration planned |
| **D06** Give every field on the ten core entities explicit name, type, required, allowed_values, unit, unique, and validation metadata. | `schema/data_dictionary.yaml`, `tools/generate_schema.py` | `test_schema_generation.py::test_dictionary_fields_have_the_required_named_shape` | `docs/DATA_DICTIONARY.md` ; status: Implemented and tested |
| **D07** Add PaymentAllocation, PromiseReconciliation, CaseStateHistory, DecisionLog, and effective-dated ContactPreference history. | `schema/data_dictionary.yaml`, `schema/schema.sql` | `test_schema_generation.py` | `docs/ER.md`, `docs/DATA_DICTIONARY.md` ; status: Implemented; ContactPreference uses effective_from/effective_to |
| **D08** Hand-maintain SQL with primary/foreign keys, enum checks, and indexes for foreign keys. | `schema/schema.sql` | `test_schema_generation.py::test_handwritten_sql_has_fk_constraints_checks_and_fk_indexes` | `docs/ER.md` ; status: Implemented and tested; SQL is not generated |
| **D09** Document Mermaid ER and relationship cardinalities, including optional associations and zero-or-one open loan cases. | `docs/ER.md`, `schema/schema.sql` | `test_schema_generation.py::test_dictionary_and_cardinality_documentation_cover_schema` | `docs/ER.md` ; status: Implemented; partial unique index enforces at most one open loan case |
| **D10** Assign citeable IDs to every policy rule and include scoring/reconciliation settings. | `config/policy.yaml` | `test_policy_config.py` | README; `docs/TRACEABILITY.md` ; status: Implemented and tested |
| **D11** Provide make_id and helpers for loan, installment, case, contact, and payment ID formats. | `ids.py` | `tests/test_ids.py` | `docs/GENERATION.md` ; status: Implemented and tested |
| **D12** Centralize the fixed-seed NumPy generator and named child streams in rng.py. | `rng.py`, `settings.py` | `test_foundations.py::EntityRandomStreamsTests` | `docs/GENERATION.md` ; status: Singleton stream registry implemented; generator integration planned |

## Business context and scope

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| **B01** Prioritize overdue accounts, schedule contact tasks, and monitor commitments without aggressive or unlawful practices. | `config/policy.yaml`, `prioritization.py`, `contacts.py`, `reconciliation.py` | `test_policy_config.py`, `test_prioritization.py`, `test_contact_policy.py`, `test_reconciliation.py` | README; `docs/DATA_DICTIONARY.md` ; status: Example policy defaults defined; runtime enforcement planned |
| **B02** Build an end-to-end workflow for prioritization, compliant contact scheduling, and commitment monitoring. | `generator.py`, `prioritization.py`, `contacts.py`, `reconciliation.py` | `test_workflow.py` | README; `docs/ARCHITECTURE.md` ; status: Planned |
| **B03** Expose key decisions and exceptions, preserve traceability, and produce measurable outputs. | `models.py`, `prioritization.py`, `validation.py` | `test_decision_traceability.py`, `test_metrics.py` | `docs/ARCHITECTURE.md`; `docs/VALIDATION.md` ; status: Planned |
| **B04** Medium complexity requires related entities, conditional rules, an exception path, and meaningful evaluation metrics. | All domain modules | `test_workflow.py`, `test_exceptions.py`, `test_metrics.py` | `docs/ARCHITECTURE.md`; `docs/VALIDATION.md` ; status: Planned |
| **B05** Primary actors are the customer/account holder, operations analyst, risk/compliance reviewer, and system administrator. | `models.py`, `contacts.py` | `test_actor_workflows.py` | `docs/ARCHITECTURE.md` ; status: Planned |

## Workflow rules and entities

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| **W01** Generate/reference Customer, Account, Loan, Installment, and DelinquencySnapshot master data first. | `models.py`, `generator.py` | `test_generation_order.py` | `docs/DATA_DICTIONARY.md` ; status: Planned |
| **W02** Generate dependent transaction/event records using valid parent IDs. | `generator.py`, `validation.py` | `test_foreign_keys.py` | `docs/ARCHITECTURE.md` ; status: Planned |
| **W03** Create loan schedules and installment due dates. | `generator.py` | `test_schedule_generation.py` | `docs/DATA_DICTIONARY.md` ; status: Planned |
| **W04** Generate payment histories. | `generator.py`, `reconciliation.py` | `test_payment_history.py` | `docs/ARCHITECTURE.md` ; status: Planned |
| **W05** Derive days-past-due and arrears. | `generator.py`, `models.py` | `test_delinquency_calculations.py` | `docs/DATA_DICTIONARY.md` ; status: Planned |
| **W06** Create contact preferences and permissible contact windows. | `config/policy.yaml`, `contacts.py`, `generator.py` | `test_policy_config.py`, `test_contact_policy.py` | `docs/DATA_DICTIONARY.md`, README ; status: Example windows and weekly attempt cap defined; runtime enforcement planned |
| **W07** Score cases from balance, age, and risk. | `config/policy.yaml`, `prioritization.py` | `test_policy_config.py`, `test_prioritization.py` | `docs/ARCHITECTURE.md` ; status: Example weights and DPD buckets defined; runtime scoring planned |
| **W08** Record contact outcomes and promises. | `contacts.py`, `models.py` | `test_contact_events.py`, `test_promise_lifecycle.py` | `docs/DATA_DICTIONARY.md` ; status: Planned |
| **W09** Reconcile payments to commitments. | `reconciliation.py` | `test_reconciliation.py` | `docs/VALIDATION.md` ; status: Planned |
| **W10** Persist state changes as explicit records/events where relevant; do not overwrite history. | `models.py`, `contacts.py`, `reconciliation.py` | `test_event_history.py` | `docs/ARCHITECTURE.md` ; status: Planned |
| **W11** Core entities are Customer, Account, Loan, Installment, DelinquencySnapshot, ContactPreference, ContactAttempt, PromiseToPay, Payment, and CollectionCase. | `schema/data_dictionary.yaml` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md` ; status: Schema defined; domain implementation planned |
| **W12** Define a primary key for every entity and foreign keys for every relationship. | `schema/data_dictionary.yaml`, `schema/schema.sql` | `test_schema_generation.py` | `schema/schema.sql` ; status: Schema constraints defined and tested |
| **W13** Document cardinality (1:1, 1:N, N:M), optional relationships, effective dates, and lifecycle states. | `schema/data_dictionary.yaml` | `test_schema_generation.py` | `docs/ER.md`, `docs/DATA_DICTIONARY.md` ; status: Cardinality/optionality documented; lifecycle runtime planned |
| **W14** Use bridge tables for many-to-many relationships; retain event history for state changes; validate all joins. | `schema/data_dictionary.yaml`, `schema/schema.sql` | `test_schema_generation.py` | `docs/ER.md`, `docs/DATA_DICTIONARY.md` ; status: Allocation and reconciliation bridges plus case/decision event records defined; runtime join validation planned |
| **W15** Deliberate anomaly cases retain an issue_type/ground_truth label instead of silently corrupting unrelated rows. | `generator.py`, `models.py`, `validation.py` | `test_labeled_anomalies.py` | `docs/VALIDATION.md` ; status: Planned |

## IDs, generation, and data coverage

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| **G01** Use the LOAN-2026-000001 ID form. | `ids.py`, `generator.py` | `test_ids.py` | `docs/DATA_DICTIONARY.md` ; status: ID helper implemented; generator integration planned |
| **G02** Use INS-<loan-id>-001 installment IDs. | `ids.py`, `generator.py` | `test_ids.py` | `docs/DATA_DICTIONARY.md` ; status: ID helper implemented; generator integration planned |
| **G03** Use COL-2026-000001 collection-case IDs. | `ids.py`, `generator.py` | `test_ids.py` | `docs/DATA_DICTIONARY.md` ; status: ID helper implemented; generator integration planned |
| **G04** Use CTP-<case-id>-001 contact-attempt IDs. | `ids.py`, `generator.py` | `test_ids.py` | `docs/DATA_DICTIONARY.md` ; status: ID helper implemented; generator integration planned |
| **G05** Use PMT-2026-000001 payment IDs. | `ids.py`, `generator.py` | `test_ids.py` | `docs/DATA_DICTIONARY.md` ; status: ID helper implemented; generator integration planned |
| **G06** Write a data dictionary covering all ten named entities. | `schema/data_dictionary.yaml`, `tools/generate_schema.py` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md` ; status: Complete; includes four additional history/bridge tables |
| **G07** Specify every field's type, required/optional status, allowed values, units, uniqueness, and validation rule. | `schema/data_dictionary.yaml`, `tools/generate_schema.py` | `test_schema_generation.py` | `docs/DATA_DICTIONARY.md` ; status: Complete |
| **G08** Create parent/master tables before child and event tables. | `generator.py` | `test_generation_order.py` | `docs/ARCHITECTURE.md` ; status: Planned |
| **G09** Keep counters zero-padded, IDs immutable, and referenced IDs exactly consistent across files. | `ids.py`, `generator.py`, `validation.py` | `test_foundations.py`, `test_foreign_keys.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` ; status: ID foundation implemented; cross-file validation planned |
| **G10** Generate 10,000 loans and 30,000 installments across 12 months. | `generator.py` | `test_full_scale_profile.py` | README; `docs/GENERATION.md` ; status: Planned |
| **G11** Include partial payments, missed promises, disputes, hardship flags, paid-off accounts, and contact restrictions. | `generator.py` | `test_coverage_profile.py` | `docs/GENERATION.md` ; status: Planned |
| **G12** Use fixed seed 20261022 (or another documented fixed seed). | `settings.py`, `rng.py`, `generator.py` | `test_foundations.py`, `test_reproducibility.py` | README; `docs/GENERATION.md` ; status: Fixed seed and child-stream foundations implemented; dataset reproducibility planned |
| **G13** Parameterize scale so starter and full datasets use the same generator. | `generator.py`, `cli.py` | `test_scale_profiles.py` | README; `docs/GENERATION.md` ; status: Planned |
| **G14** Generate valid baseline records before injecting labelled edge cases. | `generator.py` | `test_labeled_anomalies.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` ; status: Planned |
| **G15** Include the paid account remaining in collection case. | `generator.py`, `validation.py` | `test_edge_cases.py` | `docs/VALIDATION.md` ; status: Planned |
| **G16** Include contact outside the allowed window case. | `generator.py`, `contacts.py`, `validation.py` | `test_edge_cases.py`, `test_contact_policy.py` | `docs/VALIDATION.md` ; status: Planned |
| **G17** Include payment allocated to the wrong installment case. | `generator.py`, `reconciliation.py`, `validation.py` | `test_edge_cases.py`, `test_reconciliation.py` | `docs/VALIDATION.md` ; status: Planned |
| **G18** Include promise amount exceeding arrears case. | `generator.py`, `reconciliation.py`, `validation.py` | `test_edge_cases.py`, `test_promise_lifecycle.py` | `docs/VALIDATION.md` ; status: Planned |
| **G19** Include disputed debt treated as confirmed case. | `generator.py`, `prioritization.py`, `validation.py` | `test_edge_cases.py` | `docs/VALIDATION.md` ; status: Planned |
| **G20** Calculate totals, balances, scores, statuses, and dates from source records rather than independently generating them. | `generator.py`, `prioritization.py`, `reconciliation.py` | `test_derived_values.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` ; status: Planned |
| **G21** Export separate ground_truth.csv/json for known anomalies, expected decisions, or labels. | `generator.py` | `test_ground_truth_separation.py` | `docs/GENERATION.md` ; status: Planned |
| **G22** Never leak ground-truth labels into input features. | `generator.py`, `validation.py` | `test_ground_truth_separation.py` | `docs/VALIDATION.md` ; status: Planned |
| **G23** Keep the generator and its fixed seed as the source of reproducible synthetic records. | `generator.py` | `test_reproducibility.py` | `docs/GENERATION.md` ; status: Planned |

## Validation and evaluation

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| **V01** Validate primary-key uniqueness. | `validation.py` | `test_primary_keys.py` | `docs/VALIDATION.md` ; status: Planned |
| **V02** Validate foreign-key integrity. | `validation.py` | `test_foreign_keys.py` | `docs/VALIDATION.md` ; status: Planned |
| **V03** Validate allowed enums. | `validation.py` | `test_allowed_values.py` | `docs/VALIDATION.md` ; status: Planned |
| **V04** Validate date ordering. | `validation.py` | `test_date_ordering.py` | `docs/VALIDATION.md` ; status: Planned |
| **V05** Validate arithmetic reconciliation. | `validation.py`, `reconciliation.py` | `test_reconciliation.py` | `docs/VALIDATION.md` ; status: Planned |
| **V06** Validate lifecycle transitions. | `validation.py`, `models.py` | `test_lifecycle_transitions.py` | `docs/VALIDATION.md` ; status: Planned |
| **V07** Validate duplicate checks. | `validation.py` | `test_duplicates.py` | `docs/VALIDATION.md` ; status: Planned |
| **V08** Ensure arrears calculations reconcile. | `reconciliation.py`, `validation.py` | `test_delinquency_calculations.py` | `docs/VALIDATION.md` ; status: Planned |
| **V09** Make prioritization explainable. | `prioritization.py` | `test_prioritization.py` | `docs/ARCHITECTURE.md` ; status: Planned |
| **V10** Enforce contact restrictions. | `config/policy.yaml`, `contacts.py`, `validation.py` | `test_policy_config.py`, `test_contact_policy.py` | `docs/VALIDATION.md` ; status: Dispute and hardship hold defaults defined; runtime enforcement planned |
| **V11** Make promise outcomes match subsequent payments. | `reconciliation.py` | `test_reconciliation.py`, `test_promise_lifecycle.py` | `docs/VALIDATION.md` ; status: Planned |
| **V12** Evaluate realistic distributions and meaningful variation. | `generator.py`, `validation.py` | `test_distribution_metrics.py` | `docs/VALIDATION.md` ; status: Planned |
| **V13** Evaluate consistent IDs and valid joins. | `generator.py`, `validation.py` | `test_id_conventions.py`, `test_foreign_keys.py` | `docs/VALIDATION.md` ; status: Planned |
| **V14** Evaluate dependency/lifecycle consistency across entities. | `models.py`, `validation.py` | `test_lifecycle_transitions.py`, `test_relationships.py` | `docs/VALIDATION.md` ; status: Planned |
| **V15** Evaluate correct derived values and reconciliation. | `generator.py`, `reconciliation.py`, `validation.py` | `test_derived_values.py`, `test_reconciliation.py` | `docs/VALIDATION.md` ; status: Planned |
| **V16** Cover normal, boundary, failure, and exception scenarios. | `generator.py`, `validation.py` | `test_coverage_profile.py`, `test_edge_cases.py` | `docs/VALIDATION.md` ; status: Planned |
| **V17** Keep ground truth separate. | `generator.py`, `validation.py` | `test_ground_truth_separation.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` ; status: Planned |
| **V18** Demonstrate fixed-seed reproducibility. | `generator.py` | `test_reproducibility.py` | `docs/GENERATION.md` ; status: Planned |
| **V19** Provide documentation, fixed seed, source manifest, and validation summary. | `generator.py`, `validation.py` | `test_export_manifest.py` | README; `docs/GENERATION.md`; `docs/VALIDATION.md` ; status: Planned |
| **V20** Regenerate twice with the same seed and compare row counts and checksums. | `generator.py`, `validation.py` | `test_reproducibility.py` | `docs/GENERATION.md`; `docs/VALIDATION.md` ; status: Planned |

## Exports, provenance, and submission

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| **P01** Export CSV, JSON, and SQL seed data. | `generator.py` | `test_export_formats.py` | `docs/GENERATION.md` ; status: Planned |
| **P02** Include README, schema/data dictionary, generator command, fixed seed, source manifest, and validation summary. | `cli.py`, `generator.py`, `validation.py` | `test_export_manifest.py` | README; `docs/DATA_DICTIONARY.md`; `docs/GENERATION.md`; `docs/VALIDATION.md` ; status: README and this matrix exist; remaining docs planned |
| **P03** External data is optional. | `generator.py` | `test_synthetic_only_mode.py` | README; `docs/GENERATION.md` ; status: Planned |
| **P04** For any external source, record URL, dataset/version, retrieval date, license/terms, attribution, transformations, and discarded fields. | `generator.py` | `test_source_manifest.py` | `docs/GENERATION.md` ; status: Planned; no external data currently used |
| **P05** Use only legally accessible and redistributable data; do not bypass access controls or collect confidential/personal information. | `generator.py` | `test_synthetic_only_mode.py`, `test_source_manifest.py` | README; `docs/GENERATION.md` ; status: No external or personal data included |
| **P06** If licensing or suitability is unclear, use synthetic data and cite public reference data only for schema inspiration. | `generator.py` | `test_synthetic_only_mode.py` | `docs/GENERATION.md` ; status: Planned |
| **P07** Push the code to a public GitHub repository before submission. | Repository setup/release process | `git ls-remote origin` | README ; status: Public repository verified; checklist changes pushed to `main` as `7dd688c` |
| **P08** Add a README explaining how to run it. | `cli.py` | `test_cli.py` | README ; status: Scaffold usage instructions added; data-generation command awaits implementation |
| **P09** Include any tests requested by the problem. | All domain modules | `tests/` | README; this matrix ; status: Smoke test exists; domain tests are planned |
| **P10** Create the repository, `pyproject.toml`, Makefile, and CI-less skeleton. | Project root and `src/yottaflex_debt_collection/` | `test_cli.py` | README; this matrix ; status: Scaffold created; no CI workflow add |


## H0-2 and H2-7 checklist

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| Initialize the local repository, create/confirm its public GitHub repository, and push the skeleton. | Git repository; GitHub remote | `git ls-remote origin` | README ; status: Git initialized; existing repository `Pavaneswar630/yottaflex-debt-collection-engine` confirmed public; changes pushed to `main` |
| Create Makefile stubs for `setup`, `data`, `data-starter`, `validate`, `repro`, `test`, `api`, `ui`, `demo`, and `eval-ai`. | `Makefile` | `tests/test_makefile_targets.py` | README |
| Record the ambiguity that `CTP-<case-id>-001` is not tied to an entity; assume ContactAttempt, add `PTP-<case-id>-001` for PromiseToPay, and log the customer question. | `ids.py`, `schema/data_dictionary.yaml` | `tests/test_ids.py` | `docs/ASSUMPTIONS.md` ; status: customer confirmation pending |
| Assume three installments per loan because 30,000 / 10,000 = 3. | `settings.py` | `test_foundations.py::ReproducibilityDefaultsTests` | `docs/ASSUMPTIONS.md` |
| Use Customer, Account, and CaseStateHistory IDs `CUS-000001`, `ACC-000001`, and `CSH-000001`. | `ids.py`, `schema/data_dictionary.yaml`, `schema/schema.sql` | `tests/test_ids.py` | `docs/ASSUMPTIONS.md` |
| Fix the as-of date to 2026-10-31 and define a fixed generation date. | `settings.py` | `test_foundations.py::ReproducibilityDefaultsTests` | `docs/ASSUMPTIONS.md`, `docs/GENERATION.md` |
| Validate the dictionary using a small Pydantic loader. | `schema_loader.py` | `tests/test_schema_loader.py` | `schema/data_dictionary.yaml` |
| Keep the local changes committed and push them to the already-existing public GitHub repository. | Git repository; GitHub remote | `git status`, `git ls-remote` | README ; status: Commit `7dd688c` pushed; branch verified on remote |

## Numbered workflow rules and generation steps

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| Business rule 1: Generate/reference Customer, Account, Loan, Installment, and DelinquencySnapshot master data first. | `generator.py`, `schema/data_dictionary.yaml` | `test_generator.py`, `test_schema_loader.py` | `docs/DATA_DICTIONARY.md`, `docs/GENERATION.md` ; status: Customer, Account, Loan, Installment, and derived snapshots generated in dependency order |
| Business rule 2: Generate dependent transaction/event records using valid parent IDs. | `generator.py`, `validation.py` | `test_generator.py` | `docs/GENERATION.md` ; status: Generated contacts preferences, disputes, hardship, payments, and allocations have validated parent IDs |
| Business rule 3: Create schedules/due dates, payment histories, derived DPD/arrears, contact preferences/windows, scores, contact outcomes/promises, and payment reconciliation. | `generator.py`, `prioritization.py`, `contacts.py`, `reconciliation.py` | `test_generator.py`, `test_workflow.py`, `test_reconciliation.py` | `docs/GENERATION.md` ; status: Schedules, synthetic payments, contact preferences, allocation remainders, and derived delinquency snapshots implemented; contact events, promises, and prioritization workflow remain planned |
| Business rule 4: Persist state changes as explicit events and never overwrite history. | `case_state_history`, `decision_log`, `contacts.py` | `test_event_history.py` | `docs/ER.md` ; status: Schema defined; runtime event persistence planned |
| Business rule 5: Generate valid baseline data before labeled anomalies; do not corrupt unrelated records. | `generator.py`, `ground_truth` | `test_labeled_anomalies.py` | `docs/VALIDATION.md` ; status: Planned |
| Step 1: Write a field-level data dictionary for the ten core entities. | `schema/data_dictionary.yaml`, `schema_loader.py` | `test_schema_generation.py`, `test_schema_loader.py` | `docs/DATA_DICTIONARY.md` ; status: Implemented and validated |
| Step 2: Generate master records, then dependent events, schedules, payments, derived delinquency, preferences, scores, contacts, promises, and reconciliations. | `generator.py`, `reconciliation.py` | `test_generator.py` | `docs/GENERATION.md` ; status: Master data, schedules, contact preferences, disputes, hardship, payments, allocations, and dated delinquency snapshots implemented; remaining workflow outputs planned |
| Step 3: Apply deterministic zero-padded IDs and preserve references exactly across exports. | `ids.py`, `generator.py` | `test_ids.py`, `test_generator.py` | `docs/GENERATION.md` ; status: Generated CSVs use deterministic IDs and validated parent references |
| Step 4: Generate 10,000 loans and 30,000 installments across 12 months; include required coverage with one seeded parameterized generator. | `generator.py`, `rng.py`, `settings.py` | `test_generator.py` | README, `docs/GENERATION.md` ; status: Default scale and fixed-seed CLI implemented; segment mix is probabilistic; unrelated required edge-case coverage remains planned |
| Step 5: Create valid baseline records, then inject labeled required anomalies. | `generator.py`, `ground_truth` | `test_labeled_anomalies.py`, `test_edge_cases.py` | `docs/VALIDATION.md` ; status: Planned |
| Step 6: Derive totals, balances, scores, statuses, and dates from source records. | `generator.py`, `prioritization.py`, `reconciliation.py` | `test_generator.py` | `docs/GENERATION.md` ; status: Installment amounts, payment allocations, unapplied amounts, paid/partial statuses, snapshot arrears, DPD, and risk scores are derived; case prioritization scores remain planned |
| Step 7: Export separate ground truth without leaking labels into model input features. | `generator.py`, `validation.py` | `test_generator.py` | `docs/GENERATION.md` ; status: Latent segments exported separately and absent from input CSVs |
| Step 8: Validate uniqueness, foreign keys, enums, dates, arithmetic, lifecycle, and duplicates. | `generator.py`, `validation.py`, `schema_loader.py` | `test_generator.py`, `test_schema_loader.py` | `docs/GENERATION.md`, `docs/DATA_DICTIONARY.md` ; status: Generated-data keys, references, schedules, contact windows, payment reconciliation, and snapshot calculations are validated; broader workflow lifecycle checks remain planned |
| Step 9: Export CSV/JSON/SQL plus README, schema, generator command, seed, source manifest, and validation summary. | `generator.py`, `cli.py`, `validation.py` | `test_generator.py` | README, `docs/DATA_DICTIONARY.md`, `docs/GENERATION.md` ; status: CSV subset and documented command implemented; JSON/SQL exports and source manifest remain planned |
| Step 10: Regenerate twice with the same seed and compare row counts and checksums. | `generator.py`, `rng.py`, `validation.py` | `test_generator.py` | `docs/GENERATION.md` ; status: Fixed-seed output rows and CSV checksums verified in tests |

## Required negative scenarios

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| Edge case: a paid account remains in collection. | `generator.py`, `validation.py`, `R-PAIDOFF-01` | `test_edge_cases.py` | `docs/VALIDATION.md` ; status: Planned |
| Edge case: contact occurs outside the allowed window. | `generator.py`, `contacts.py`, `R-CONTACT-01` | `test_edge_cases.py`, `test_contact_policy.py` | `docs/VALIDATION.md` ; status: Planned |
| Edge case: payment is allocated to the wrong installment. | `generator.py`, `reconciliation.py`, `validation.py` | `test_edge_cases.py`, `test_reconciliation.py` | `docs/VALIDATION.md` ; status: Planned |
| Edge case: promise amount exceeds arrears. | `generator.py`, `reconciliation.py`, `validation.py` | `test_edge_cases.py`, `test_promise_lifecycle.py` | `docs/VALIDATION.md` ; status: Planned |
| Edge case: disputed debt is treated as confirmed. | `generator.py`, `prioritization.py`, `R-DISPUTE-01` | `test_edge_cases.py` | `docs/VALIDATION.md` ; status: Planned |

## Acceptance criteria

| Brief sentence | Module | Test | Doc |
|---|---|---|---|
| Acceptance 1: Arrears calculations reconcile to source installments and allocations. | `generator.py`, `validation.py` | `test_generator.py` (slow loop-based reference) | `docs/GENERATION.md` ; status: Snapshot arrears and DPD match an independent loop-based reference implementation |
| Acceptance 2: Prioritization decisions are explainable from balance, age, risk, and policy. | `prioritization.py`, `config/policy.yaml`, `decision_log` | `test_prioritization.py`, `test_decision_traceability.py` | `docs/ARCHITECTURE.md` ; status: Planned |
| Acceptance 3: Contact restrictions are enforced using local time and account-level attempt history. | `contacts.py`, `config/policy.yaml` | `test_contact_policy.py` | `docs/VALIDATION.md` ; status: Planned |
| Acceptance 4: Promise outcomes match subsequent reconciled payments. | `reconciliation.py`, `promise_reconciliation` | `test_reconciliation.py`, `test_promise_lifecycle.py` | `docs/VALIDATION.md` ; status: Planned |
| Acceptance 5: Regenerating with the same seed produces matching row counts and checksums. | `generator.py`, `rng.py`, `validation.py` | `test_generator.py` | `docs/GENERATION.md` ; status: Verified for generated CSV outputs |
