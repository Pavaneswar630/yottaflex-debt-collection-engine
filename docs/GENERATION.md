# Synthetic dataset generation

The CLI generates deterministic synthetic records without external or personal data. It accepts `--loans` and `--seed`; `--output-dir` optionally changes the output root:

```shell
python -m yottaflex_debt_collection --loans 10000 --seed 20261022
python -m yottaflex_debt_collection --loans 100 --seed 20261022 --output-dir sample
```

By default, entity CSVs are written to `data/` and behavior labels are written separately to `ground_truth/latent_segments.csv`. The labels never appear in customer, account, loan, installment, contact-preference, dispute, hardship, payment, or allocation files. Repeating the command with the same arguments produces byte-identical CSVs.

Generation uses one `EntityRandomStreams` instance seeded from `--seed`, with named child streams for customers, accounts, loans, preferences, disputes, hardship requests, payments, and ground truth. Adding a child stream at the end of `ENTITY_STREAMS` preserves existing stream assignments. IDs are deterministic, zero-padded strings issued by `IdFactory`; all money values are integer cents.

The baseline creates two accounts per customer where scale permits and one loan per account. Each loan has three quarterly installments over twelve months. Principal is divided evenly in cents, with any remainder added to the final installment; interest is calculated deterministically from the loan rate. Originations and due dates are fixed relative to the project’s as-of date, `2026-10-31`; generation never consults the system clock.

Latent behavior is assigned using a seeded categorical distribution: `on_time` 55%, `late_cure` 15%, `partial` 10%, `rolling` 8%, `never_pay` 5%, and `early_payoff` 7%. These are target probabilities, so observed proportions vary by seed and sample size. Payment records are derived from the assigned behavior and scheduled amounts. Allocations consume each account’s oldest outstanding installments first. `payment.unapplied_amount` records any remainder after allocations, and the generator validates that allocations plus the unapplied amount equal each payment.

Contact preferences are effective-dated, use the customer’s IANA timezone, include a do-not-contact restriction, and restrict local contact hours to a subset of 08:00–19:00. Synthetic dispute and hardship records are optional; their account/loan references and lifecycle timestamps are validated. The corresponding records are defined in the YAML dictionary and hand-maintained SQL schema.

Generated directories are ignored by Git. Run `python -m pytest tests/test_generator.py` to check row counts, foreign keys, distribution, schedule arithmetic, restrictions, allocation reconciliation, and repeatability.

The existing ID helpers also include `loan_id`, `installment_id`, `case_id`, `contact_id`, and `payment_id`. The schema models event history and other workflow entities beyond the current generator’s export scope; see `TRACEABILITY.md` for remaining end-to-end functionality.
