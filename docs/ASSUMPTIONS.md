# Assumptions and questions

These are the fixed assumptions used by the synthetic demonstration. They are implementation choices, not customer-confirmed legal or business requirements. Reconfirm A01 before treating that identifier convention as a production contract.

| ID | Assumption or question | Current treatment | Status |
|---|---|---|---|
| A01 | The brief specifies `CTP-<case-id>-001` but does not identify which entity owns this ID pattern. | For this synthetic implementation, `CTP-<case-id>-001` identifies `ContactAttempt`; `PTP-<case-id>-001` identifies `PromiseToPay`. Confirm the convention with the intended owner before production use. | Working assumption; production confirmation outstanding |
| A02 | The requested 30,000 installments across 10,000 loans imply three installments per loan. | Set `INSTALLMENTS_PER_LOAN = 3`; this satisfies the requested baseline counts. | Working assumption |
| A03 | Customer, Account, and CaseStateHistory IDs need formats without a year segment. | Use `CUS-000001`, `ACC-000001`, and `CSH-000001`. | Working assumption |
| A04 | A fixed generation date is required alongside an as-of date. | Use `2026-10-31` as both `AS_OF_DATE` and `GENERATION_DATE`; no runtime clock is consulted. | Working assumption |

Changing an assumption requires updating this table, the ID/schema contract, and its tests together. The project does not claim that any assumption is legally approved or suitable for a real portfolio.
