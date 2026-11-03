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

For a snapshot date `D`, arrears are the sum of unpaid balances only for installments with `due_date <= D`; payments reduce those balances only when their posted date is on or before `D`. DPD is the number of calendar days from `D` to the oldest due date with an unpaid balance, or zero when no due installment is unpaid. Snapshots are generated at every month-end from origination through `2026-10-31`, on the date DPD first reaches the case-opening threshold, and at the fixed as-of date. If different triggers share a date, each is retained as a separate append-only snapshot with its own `snapshot_reason`. Risk score is a deterministic representation of the generated customer risk band (low 20, medium 45, high 70, critical 90).

`R-CASE-01` opens one collection case when DPD first reaches its configured threshold (one day by default); its `opened_at` is that exact crossing date. The score is evaluated at the fixed as-of date and stored in `scored_at`. Components are normalized: balance is `min(as-of arrears / original principal, 1)`, age is the configured as-of DPD-bucket score divided by 100, and risk is the customer risk score divided by 100. Priority is `100 × (0.40 × balance + 0.35 × age + 0.25 × risk)`, rounded to two decimals. Tiers are P1 for scores at least 70, P2 for scores at least 40, and P3 otherwise. Semicolon-delimited reason codes record the threshold crossing plus balance, age-bucket, and risk-band explanations. These defaults are documented in `config/policy.yaml`.

Suppression checks follow `config/policy.yaml`'s `first_match_order`; the first active rule is recorded as `collection_case.suppression_rule_id`, and later matches are not considered. The order is paid-off, active dispute, requested/approved hardship, then active cease-contact preference. A paid-off case is resolved; dispute, hardship, and cease-contact cases are paused; otherwise the case remains open. This preserves the case record while suppressing outbound collection activity for the selected rule. The current generator treats an effective-dated `ContactPreference.do_not_contact` value as the cease-contact signal.

Every collection case receives exactly one `DecisionLog` record. Suppressed cases cite their first matching suppression rule and are routed to review or closed for paid-off loans. Other cases are scheduled at the earliest permissible local time on the fixed as-of date, or blocked when the effective-dated preference leaves no valid window, an active cease-contact restriction applies, or the account has reached the configured rolling weekly capacity. Scheduled reservations count toward the account-level cap as specified by `R-CONTACT-02`; the current baseline has one loan per account, while scheduler tests exercise contention across decisions. `next_action_at` is populated only for allowed schedules. Decisions retain their policy rule ID, outcome, reason, score, as-of date, and deterministic `DEC-2026-` ID.

Generated directories are ignored by Git. Run `python -m pytest tests/test_generator.py` to check row counts, foreign keys, distribution, schedule arithmetic, restrictions, allocation reconciliation, and repeatability.

The existing ID helpers also include `loan_id`, `installment_id`, `case_id`, `contact_id`, and `payment_id`. The schema models event history and other workflow entities beyond the current generator’s export scope; see `TRACEABILITY.md` for remaining end-to-end functionality.
