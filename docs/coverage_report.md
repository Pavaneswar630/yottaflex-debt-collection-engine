# Validation and detector coverage

## Integrity checks

`python -m yottaflex_debt_collection.integrity --data-dir data/full` validates the exported input tables for:

- primary-key uniqueness, including composite bridge keys;
- foreign-key references;
- documented enum values;
- parseable dates and effective/lifecycle date ordering;
- installment, principal-schedule, payment-allocation, and unapplied-payment arithmetic;
- case and promise lifecycle continuity and terminal-state consistency.

Intentional scenario anomalies may violate operational policy, but the input must retain structurally valid identifiers, references, dates, arithmetic, enums, and lifecycle records.

## Blind detectors

`python -m yottaflex_debt_collection.detectors --data-dir data/full --output reports/detections.csv` uses only input tables and starts with these three types:

| Issue type | Detection rule |
|---|---|
| `paid_account_in_collection` | A paid-off loan has an open or paused collection case. |
| `contact_outside_allowed_window` | The attempt is outside the effective preference window or policy window of 08:00 to 19:00 in the customer timezone. |
| `payment_allocated_to_wrong_installment` | An allocation targets a later installment while an older due balance remains unpaid. Early payoff allocations are permitted. |

`tests/test_integrity_detectors.py::test_blind_detector_module_cannot_reference_label_locations` prevents the detector module from importing or naming the label directory or evaluator. Only the separate evaluation module reads labels.

## Minimum-count assertions

The coverage test generates 1,000 loans with the fixed seed `20261022` and five requested examples per labeled type. It asserts these minimums:

| Coverage family | Required minimum |
|---|---:|
| Normal | 1 collection case not used by a primary labeled scenario |
| Boundary: exact 08:00 contact | 5 |
| Boundary: promise equal to arrears | 5 |
| Failure: out-of-window contact | 5 |
| Failure: wrong-installment allocation | 5 |
| Failure: promise exceeds arrears | 5 |
| Exception: paid-off loan remains in collection | 5 |
| Exception: disputed debt treated as confirmed | 5 |

Run the assertions with:

```powershell
python -m pytest tests/test_integrity_detectors.py -q
```

## Evaluation

Run `make detect` then `make evaluate`. The evaluation report at `reports/detector_metrics.md` contains true positives, false positives, false negatives, precision, recall, and F1 for each of the three detector types. Scores are computed against primary labels only; derived-recalculation labels are excluded.
