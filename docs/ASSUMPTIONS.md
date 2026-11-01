# Assumptions and questions

These are explicit working assumptions for the synthetic-data scope. Any item marked as a question needs confirmation before the corresponding ID contract or generation behavior is treated as final.

| ID | Assumption or question | Current treatment | Status |
|---|---|---|---|
| A01 | **Question for the customer:** the brief specifies `CTP-<case-id>-001` but does not identify which entity owns this ID pattern. Should `CTP` identify a ContactAttempt? | Treat `CTP-<case-id>-001` as `ContactAttempt`; use `PTP-<case-id>-001` for `PromiseToPay`. | Pending customer confirmation |
| A02 | The requested 30,000 installments across 10,000 loans imply three installments per loan. | Set `INSTALLMENTS_PER_LOAN = 3`; this satisfies the requested baseline counts. | Working assumption |
| A03 | Customer, Account, and CaseStateHistory IDs need formats without a year segment. | Use `CUS-000001`, `ACC-000001`, and `CSH-000001`. | Working assumption |
| A04 | A fixed generation date is required alongside an as-of date. | Use `2026-10-31` as both `AS_OF_DATE` and `GENERATION_DATE`; no runtime clock is consulted. | Working assumption |

Changing an assumption requires updating this table, the ID/schema contract, and its tests together.
