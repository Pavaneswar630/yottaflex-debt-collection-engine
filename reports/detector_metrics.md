# Blind detector evaluation

Scores compare detector output with primary labels; derived recalculation rows are excluded.

Dataset: `full`; loans: 10000; seed: 20261022.

| Issue type | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| paid_account_in_collection | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| contact_outside_allowed_window | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| payment_allocated_to_wrong_installment | 50 | 25 | 0 | 0.667 | 1.000 | 0.800 |
