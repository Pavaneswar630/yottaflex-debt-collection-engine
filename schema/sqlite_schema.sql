PRAGMA foreign_keys = ON;

CREATE TABLE customer (
    customer_id TEXT PRIMARY KEY,
    customer_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    risk_band TEXT NOT NULL,
    timezone TEXT NOT NULL,
    preferred_language TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE account (
    account_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customer(customer_id),
    account_status TEXT NOT NULL,
    hardship_status TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE loan (
    loan_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account(account_id),
    product_type TEXT NOT NULL,
    principal_amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    annual_interest_rate REAL NOT NULL,
    term_months INTEGER NOT NULL,
    origination_date TEXT NOT NULL,
    maturity_date TEXT NOT NULL,
    loan_status TEXT NOT NULL,
    paid_off_date TEXT
);
CREATE TABLE installment (
    installment_id TEXT PRIMARY KEY,
    loan_id TEXT NOT NULL REFERENCES loan(loan_id),
    sequence_number INTEGER NOT NULL,
    due_date TEXT NOT NULL,
    principal_due INTEGER NOT NULL,
    interest_due INTEGER NOT NULL,
    total_due INTEGER NOT NULL,
    installment_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE delinquency_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    loan_id TEXT NOT NULL REFERENCES loan(loan_id),
    snapshot_date TEXT NOT NULL,
    snapshot_reason TEXT NOT NULL,
    days_past_due INTEGER NOT NULL,
    arrears_amount INTEGER NOT NULL,
    risk_score REAL NOT NULL,
    risk_band TEXT NOT NULL,
    dispute_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE collection_case (
    case_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account(account_id),
    loan_id TEXT NOT NULL REFERENCES loan(loan_id),
    status TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    scored_at TEXT NOT NULL,
    priority_score REAL NOT NULL,
    balance_component REAL NOT NULL,
    age_component REAL NOT NULL,
    risk_component REAL NOT NULL,
    priority_tier TEXT NOT NULL,
    reason_codes TEXT NOT NULL,
    suppression_rule_id TEXT,
    next_action_at TEXT
);
CREATE TABLE contact_preference (
    contact_preference_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account(account_id),
    preferred_channel TEXT NOT NULL,
    timezone TEXT NOT NULL,
    allowed_start_time TEXT NOT NULL,
    allowed_end_time TEXT NOT NULL,
    do_not_contact INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE dispute (
    dispute_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account(account_id),
    loan_id TEXT NOT NULL REFERENCES loan(loan_id),
    filed_at TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    status TEXT NOT NULL,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE hardship_request (
    hardship_request_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account(account_id),
    loan_id TEXT NOT NULL REFERENCES loan(loan_id),
    requested_at TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    status TEXT NOT NULL,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE payment (
    payment_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES account(account_id),
    received_at TEXT NOT NULL,
    posted_at TEXT,
    amount INTEGER NOT NULL,
    unapplied_amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    status TEXT NOT NULL,
    external_reference TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE payment_allocation (
    payment_id TEXT NOT NULL REFERENCES payment(payment_id),
    installment_id TEXT NOT NULL REFERENCES installment(installment_id),
    allocated_amount INTEGER NOT NULL,
    allocated_at TEXT NOT NULL,
    PRIMARY KEY (payment_id, installment_id)
);
CREATE TABLE decision_log (
    decision_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES collection_case(case_id),
    loan_id TEXT NOT NULL REFERENCES loan(loan_id),
    rule_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT NOT NULL,
    priority_score REAL NOT NULL,
    as_of_date TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE contact_attempt (
    contact_attempt_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES collection_case(case_id),
    attempted_at TEXT NOT NULL,
    channel TEXT NOT NULL,
    outcome TEXT NOT NULL,
    agent_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE promise_to_pay (
    promise_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES collection_case(case_id),
    promised_amount INTEGER NOT NULL,
    promised_date TEXT NOT NULL,
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE TABLE promise_reconciliation (
    promise_id TEXT NOT NULL REFERENCES promise_to_pay(promise_id),
    payment_id TEXT NOT NULL REFERENCES payment(payment_id),
    reconciled_amount INTEGER NOT NULL,
    reconciled_at TEXT NOT NULL,
    match_status TEXT NOT NULL,
    PRIMARY KEY (promise_id, payment_id)
);
CREATE TABLE state_event (
    state_event_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    case_id TEXT REFERENCES collection_case(case_id),
    promise_id TEXT REFERENCES promise_to_pay(promise_id),
    previous_state TEXT,
    new_state TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    actor_type TEXT NOT NULL
);
CREATE TABLE latent_segment (
    loan_id TEXT PRIMARY KEY REFERENCES loan(loan_id),
    segment TEXT NOT NULL
);

CREATE INDEX idx_account_customer ON account(customer_id);
CREATE INDEX idx_loan_account ON loan(account_id);
CREATE INDEX idx_installment_loan_due ON installment(loan_id, due_date);
CREATE INDEX idx_snapshot_loan_date ON delinquency_snapshot(loan_id, snapshot_date);
CREATE INDEX idx_case_account ON collection_case(account_id);
CREATE INDEX idx_case_loan ON collection_case(loan_id);
CREATE INDEX idx_preference_account ON contact_preference(account_id);
CREATE INDEX idx_dispute_account ON dispute(account_id);
CREATE INDEX idx_dispute_loan ON dispute(loan_id);
CREATE INDEX idx_hardship_account ON hardship_request(account_id);
CREATE INDEX idx_hardship_loan ON hardship_request(loan_id);
CREATE INDEX idx_payment_account ON payment(account_id);
CREATE INDEX idx_allocation_installment ON payment_allocation(installment_id);
CREATE INDEX idx_decision_case ON decision_log(case_id);
CREATE INDEX idx_decision_loan ON decision_log(loan_id);
CREATE INDEX idx_attempt_case ON contact_attempt(case_id);
CREATE INDEX idx_promise_case ON promise_to_pay(case_id);
CREATE INDEX idx_reconciliation_payment ON promise_reconciliation(payment_id);
CREATE INDEX idx_state_case ON state_event(case_id);
CREATE INDEX idx_state_promise ON state_event(promise_id);

CREATE VIEW latest_snapshot AS
WITH ranked AS (
    SELECT
        snapshot.*,
        ROW_NUMBER() OVER (
            PARTITION BY loan_id
            ORDER BY
                snapshot_date DESC,
                CASE snapshot_reason
                    WHEN 'as_of' THEN 0
                    WHEN 'case_open' THEN 1
                    ELSE 2
                END,
                snapshot_id DESC
        ) AS row_number
    FROM delinquency_snapshot AS snapshot
)
SELECT * FROM ranked WHERE row_number = 1;

CREATE VIEW roll_rates AS
WITH monthly AS (
    SELECT
        loan_id,
        snapshot_date,
        CASE
            WHEN days_past_due = 0 THEN 'current'
            WHEN days_past_due <= 30 THEN '1_30'
            WHEN days_past_due <= 60 THEN '31_60'
            WHEN days_past_due <= 90 THEN '61_90'
            ELSE '90_plus'
        END AS delinquency_bucket
    FROM delinquency_snapshot
    WHERE snapshot_reason = 'month_end'
),
transitions AS (
    SELECT
        loan_id,
        LAG(delinquency_bucket) OVER (
            PARTITION BY loan_id ORDER BY snapshot_date
        ) AS from_bucket,
        delinquency_bucket AS to_bucket
    FROM monthly
)
SELECT
    from_bucket,
    to_bucket,
    COUNT(*) AS loan_transitions
FROM transitions
WHERE from_bucket IS NOT NULL
GROUP BY from_bucket, to_bucket;

CREATE VIEW promise_kept_by_segment AS
SELECT
    latent_segment.segment,
    COUNT(promise.promise_id) AS promise_count,
    SUM(CASE WHEN promise.status = 'KEPT' THEN 1 ELSE 0 END) AS kept_count,
    CASE
        WHEN COUNT(promise.promise_id) = 0 THEN 0.0
        ELSE 1.0 * SUM(CASE WHEN promise.status = 'KEPT' THEN 1 ELSE 0 END)
            / COUNT(promise.promise_id)
    END AS kept_rate
FROM latent_segment
JOIN loan ON loan.loan_id = latent_segment.loan_id
JOIN collection_case AS collection_case ON collection_case.loan_id = loan.loan_id
LEFT JOIN promise_to_pay AS promise ON promise.case_id = collection_case.case_id
GROUP BY latent_segment.segment;

CREATE VIEW cure_rate AS
WITH start_dpd AS (
    SELECT loan_id, MAX(days_past_due) AS days_past_due
    FROM delinquency_snapshot
    WHERE snapshot_reason = 'case_open'
    GROUP BY loan_id
),
cures AS (
    SELECT
        start_dpd.loan_id,
        start_dpd.days_past_due AS initial_days_past_due,
        latest.days_past_due AS latest_days_past_due
    FROM start_dpd
    JOIN latest_snapshot AS latest ON latest.loan_id = start_dpd.loan_id
)
SELECT
    COUNT(*) AS delinquent_loans,
    SUM(
        CASE
            WHEN initial_days_past_due > 0 AND latest_days_past_due = 0 THEN 1
            ELSE 0
        END
    ) AS cured_loans,
    CASE WHEN COUNT(*) = 0 THEN 0.0 ELSE
        1.0 * SUM(
            CASE
                WHEN initial_days_past_due > 0 AND latest_days_past_due = 0 THEN 1
                ELSE 0
            END
        ) / COUNT(*)
    END AS cure_rate
FROM cures;

CREATE VIEW violations_by_rule AS
SELECT
    rule_id,
    decision_type,
    outcome,
    COUNT(*) AS decision_count
FROM decision_log
WHERE outcome IN ('block', 'review', 'close')
GROUP BY rule_id, decision_type, outcome;

CREATE VIEW priority_queue AS
SELECT
    collection_case.case_id,
    collection_case.account_id,
    collection_case.loan_id,
    collection_case.status,
    collection_case.priority_score,
    collection_case.priority_tier,
    collection_case.balance_component,
    collection_case.age_component,
    collection_case.risk_component,
    collection_case.reason_codes,
    collection_case.suppression_rule_id,
    collection_case.next_action_at,
    latest_snapshot.days_past_due,
    latest_snapshot.arrears_amount,
    latest_snapshot.snapshot_date
FROM collection_case
LEFT JOIN latest_snapshot
    ON latest_snapshot.loan_id = collection_case.loan_id
WHERE collection_case.status = 'open';
