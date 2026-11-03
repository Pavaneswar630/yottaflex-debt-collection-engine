# Validation and reproducibility summary

## Reproducibility proof

- Dataset: `full` (10,000 loans)
- Seed: `20261022`
- Requested anomaly rows per type: `50`
- As-of date: `2026-10-31`
- Generation date: `2026-10-31`
- Two independent generations produced identical relative file lists.
- All exported file SHA-256 checksums matched across both generations.
- Manifest input and ground-truth row counts matched across both generations.

## Row counts

| Table | Rows |
|---|---:|
| `account` | 10,000 |
| `collection_case` | 3,742 |
| `contact_attempt` | 3,742 |
| `contact_preference` | 10,000 |
| `customer` | 5,000 |
| `decision_log` | 3,742 |
| `delinquency_snapshot` | 198,480 |
| `dispute` | 457 |
| `ground_truth.expected_decisions` | 350 |
| `ground_truth.ground_truth` | 1,111 |
| `ground_truth.latent_segments` | 10,000 |
| `hardship_request` | 834 |
| `installment` | 30,000 |
| `loan` | 10,000 |
| `payment` | 27,155 |
| `payment_allocation` | 31,594 |
| `promise_reconciliation` | 468 |
| `promise_to_pay` | 1,666 |
| `state_event` | 8,727 |

## SHA-256 checksums

| File | SHA-256 |
|---|---|
| `data/full/account.csv` | `c767f3f93549932dc1790e03bb880866be0d44b00492af4170092ff3b98bb3a3` |
| `data/full/collection_case.csv` | `0339c27d631fea5570eebd977297ba366eeb316706c36d8205970ef5ae910623` |
| `data/full/contact_attempt.csv` | `953a61a853bb60aebb249a2ffdedf05e8f84387ba6b983d7d3d0a966eb15ca12` |
| `data/full/contact_preference.csv` | `8e979bba240ee3692e85476b8fc877c34af551df7b8a0323faa50b8e1b580551` |
| `data/full/customer.csv` | `521466240e055f0fe31bf6d57fc0a0e2250d76eaf1c3775904215b2573bae135` |
| `data/full/dataset.json` | `ff4e0c2670189f2f0ea104d0c23841229eb9878dc6f499c2e173cf4ce74d7105` |
| `data/full/decision_log.csv` | `5fc155f04b09b3ada9f6bea10800ad6a0916a647da5ddd50b1e59ed138afabbb` |
| `data/full/delinquency_snapshot.csv` | `e970cfad54a2f2cdcbfe731f6b26e4be012fff4013d17b1902a87b5e1c822403` |
| `data/full/dispute.csv` | `9dbfe45a53ef79ad36d667a112510b19d8461cce534d6084f3d3cb0b09782ca0` |
| `data/full/hardship_request.csv` | `5832a3340d2d2c1affbf2f1e92c1e357bcd148df518c5c4ae995e31173cd4bf2` |
| `data/full/installment.csv` | `3463d84c55b03683b053718e116df951ceccf75115f679f58b9d972d10e7a39f` |
| `data/full/loan.csv` | `01746ad0aa8065dc6fa26998f155be7283b8d2f8572025ca306adc2b37c3f52d` |
| `data/full/manifest.json` | `e10db0173d10a96c42f6628f5a6f0a9d35502ec3cf3434a14bb9027b92bb9e71` |
| `data/full/payment.csv` | `184949175f86894a4c5bf2435ceb7f379e0900d044c110019d01f6cb32cacb8b` |
| `data/full/payment_allocation.csv` | `5c4804ee587e5a2cfab18fb63a210b67e3507f8d41e04052a134ba7dbf0833e6` |
| `data/full/promise_reconciliation.csv` | `d399f0737e535f8a7b5cd3ce1fbdc43d0ef4fadc2c46f5b08f343c3e3ac9e372` |
| `data/full/promise_to_pay.csv` | `ff9931826bd08545183f9c5acfebeadb0cdc4e941b0dd6c9d350e9db235b0efa` |
| `data/full/seed.sql` | `ac783329fc9969c2836cd141923eecf9229fc83ed6fbe786cac75f6cff1f1aea` |
| `data/full/state_event.csv` | `5151f4578f1d7bb4edb417c2e13bca2cc751afa2b07e806dcb1d360264497ce5` |
| `ground_truth/full/expected_decisions.csv` | `8491960885aa3c2ad4d88750709f124ac03b535ecc4ff2fc50b02fa270ce33b7` |
| `ground_truth/full/ground_truth.csv` | `408fea6f436e4a1cd216bce91e060f867ef51038b5a8dc4a8427cb07cd09a787` |
| `ground_truth/full/latent_segments.csv` | `3a13cb18a9e63079c37d5156c7a68e65fd54db13421ee203ea0e2ccae33d3afc` |
