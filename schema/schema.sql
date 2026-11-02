-- Hand-maintained PostgreSQL DDL.
-- Keep this schema aligned with schema/data_dictionary.yaml and docs/ER.md.

CREATE TABLE customer (
    customer_id VARCHAR(32) NOT NULL,
    customer_type VARCHAR(16) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    risk_band VARCHAR(12) NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    preferred_language VARCHAR(16),
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT customer_pkey PRIMARY KEY (customer_id),
    CONSTRAINT customer_customer_id_check CHECK (customer_id ~ '^CUS-[0-9]{6}$'),
    CONSTRAINT customer_customer_type_enum CHECK (customer_type IN ('individual', 'organization')),
    CONSTRAINT customer_display_name_check CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
    CONSTRAINT customer_risk_band_enum CHECK (risk_band IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT customer_timezone_check CHECK (length(trim(timezone)) > 0)
);

CREATE TABLE account (
    account_id VARCHAR(32) NOT NULL,
    customer_id VARCHAR(32) NOT NULL,
    account_status VARCHAR(16) NOT NULL,
    hardship_status VARCHAR(16) NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    CONSTRAINT account_pkey PRIMARY KEY (account_id),
    CONSTRAINT account_account_id_check CHECK (account_id ~ '^ACC-[0-9]{6}$'),
    CONSTRAINT account_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES customer (customer_id) ON DELETE RESTRICT,
    CONSTRAINT account_account_status_enum CHECK (account_status IN ('open', 'closed')),
    CONSTRAINT account_hardship_status_enum CHECK (hardship_status IN ('none', 'requested', 'approved', 'declined')),
    CONSTRAINT account_close_order CHECK (closed_at IS NULL OR closed_at >= opened_at),
    CONSTRAINT account_status_close_date CHECK ((account_status = 'closed') = (closed_at IS NOT NULL))
);

CREATE TABLE loan (
    loan_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    product_type VARCHAR(24) NOT NULL,
    principal_amount BIGINT NOT NULL,
    currency CHAR(3) NOT NULL,
    annual_interest_rate NUMERIC(7,4) NOT NULL,
    term_months SMALLINT NOT NULL,
    origination_date DATE NOT NULL,
    maturity_date DATE NOT NULL,
    loan_status VARCHAR(16) NOT NULL,
    paid_off_date DATE,
    CONSTRAINT loan_pkey PRIMARY KEY (loan_id),
    CONSTRAINT loan_loan_id_check CHECK (loan_id ~ '^LOAN-2026-[0-9]{6}$'),
    CONSTRAINT loan_account_id_fkey FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE RESTRICT,
    CONSTRAINT loan_product_type_enum CHECK (product_type IN ('personal', 'auto', 'mortgage', 'credit_line')),
    CONSTRAINT loan_principal_amount_check CHECK (principal_amount > 0),
    CONSTRAINT loan_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT loan_annual_interest_rate_check CHECK (annual_interest_rate BETWEEN 0 AND 100),
    CONSTRAINT loan_term_months_check CHECK (term_months > 0),
    CONSTRAINT loan_loan_status_enum CHECK (loan_status IN ('active', 'paid_off', 'defaulted', 'closed')),
    CONSTRAINT loan_date_order CHECK (maturity_date > origination_date),
    CONSTRAINT loan_paid_off_state CHECK ((loan_status = 'paid_off') = (paid_off_date IS NOT NULL)),
    CONSTRAINT loan_paid_off_date_order CHECK (paid_off_date IS NULL OR paid_off_date >= origination_date)
);

CREATE TABLE installment (
    installment_id VARCHAR(64) NOT NULL,
    loan_id VARCHAR(32) NOT NULL,
    sequence_number SMALLINT NOT NULL,
    due_date DATE NOT NULL,
    principal_due BIGINT NOT NULL,
    interest_due BIGINT NOT NULL,
    total_due BIGINT NOT NULL,
    installment_status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT installment_pkey PRIMARY KEY (installment_id),
    CONSTRAINT installment_installment_id_check CHECK (installment_id ~ '^INS-LOAN-2026-[0-9]{6}-[0-9]{3}$'),
    CONSTRAINT installment_loan_id_fkey FOREIGN KEY (loan_id) REFERENCES loan (loan_id) ON DELETE RESTRICT,
    CONSTRAINT installment_sequence_number_check CHECK (sequence_number > 0),
    CONSTRAINT installment_principal_due_check CHECK (principal_due >= 0),
    CONSTRAINT installment_interest_due_check CHECK (interest_due >= 0),
    CONSTRAINT installment_total_due_check CHECK (total_due >= 0 AND total_due = principal_due + interest_due),
    CONSTRAINT installment_installment_status_enum CHECK (installment_status IN ('scheduled', 'partially_paid', 'paid', 'past_due', 'waived')),
    CONSTRAINT installment_loan_sequence UNIQUE (loan_id, sequence_number)
);

CREATE TABLE delinquency_snapshot (
    snapshot_id VARCHAR(32) NOT NULL,
    loan_id VARCHAR(32) NOT NULL,
    snapshot_date DATE NOT NULL,
    snapshot_reason VARCHAR(12) NOT NULL,
    days_past_due INTEGER NOT NULL,
    arrears_amount BIGINT NOT NULL,
    risk_score NUMERIC(5,2) NOT NULL,
    risk_band VARCHAR(12) NOT NULL,
    dispute_status VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT delinquency_snapshot_pkey PRIMARY KEY (snapshot_id),
    CONSTRAINT delinquency_snapshot_snapshot_id_check CHECK (snapshot_id ~ '^DLS-2026-[0-9]{6}$'),
    CONSTRAINT delinquency_snapshot_loan_id_fkey FOREIGN KEY (loan_id) REFERENCES loan (loan_id) ON DELETE RESTRICT,
    CONSTRAINT delinquency_snapshot_reason_enum CHECK (snapshot_reason IN ('month_end', 'case_open', 'as_of')),
    CONSTRAINT delinquency_snapshot_days_past_due_check CHECK (days_past_due >= 0),
    CONSTRAINT delinquency_snapshot_arrears_amount_check CHECK (arrears_amount >= 0),
    CONSTRAINT delinquency_snapshot_risk_score_check CHECK (risk_score BETWEEN 0 AND 100),
    CONSTRAINT delinquency_snapshot_risk_band_enum CHECK (risk_band IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT delinquency_snapshot_dispute_status_enum CHECK (dispute_status IN ('not_disputed', 'disputed', 'under_review', 'resolved')),
    CONSTRAINT snapshot_loan_date_reason UNIQUE (loan_id, snapshot_date, snapshot_reason)
);

CREATE TABLE contact_preference (
    contact_preference_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    preferred_channel VARCHAR(12) NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    allowed_start_time TIME NOT NULL,
    allowed_end_time TIME NOT NULL,
    do_not_contact BOOLEAN NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT contact_preference_pkey PRIMARY KEY (contact_preference_id),
    CONSTRAINT contact_preference_contact_preference_id_check CHECK (contact_preference_id ~ '^CPF-2026-[0-9]{6}$'),
    CONSTRAINT contact_preference_account_id_fkey FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE RESTRICT,
    CONSTRAINT contact_preference_preferred_channel_enum CHECK (preferred_channel IN ('phone', 'email', 'sms', 'postal')),
    CONSTRAINT contact_window_order CHECK (allowed_start_time < allowed_end_time),
    CONSTRAINT contact_preference_effective_order CHECK (effective_to IS NULL OR effective_to >= effective_from),
    CONSTRAINT contact_preference_account_start UNIQUE (account_id, effective_from)
);

CREATE TABLE dispute (
    dispute_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    loan_id VARCHAR(32) NOT NULL,
    filed_at TIMESTAMPTZ NOT NULL,
    reason_code VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT dispute_pkey PRIMARY KEY (dispute_id),
    CONSTRAINT dispute_id_check CHECK (dispute_id ~ '^DIS-2026-[0-9]{6}$'),
    CONSTRAINT dispute_account_fkey FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE RESTRICT,
    CONSTRAINT dispute_loan_fkey FOREIGN KEY (loan_id) REFERENCES loan (loan_id) ON DELETE RESTRICT,
    CONSTRAINT dispute_reason_enum CHECK (
        reason_code IN ('balance_question', 'payment_not_posted', 'identity_question')
    ),
    CONSTRAINT dispute_status_enum CHECK (status IN ('under_review', 'resolved', 'withdrawn')),
    CONSTRAINT dispute_resolution_state CHECK ((status = 'under_review') = (resolved_at IS NULL)),
    CONSTRAINT dispute_resolution_order CHECK (resolved_at IS NULL OR resolved_at >= filed_at)
);

CREATE TABLE hardship_request (
    hardship_request_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    loan_id VARCHAR(32) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    reason_code VARCHAR(24) NOT NULL,
    status VARCHAR(12) NOT NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT hardship_request_pkey PRIMARY KEY (hardship_request_id),
    CONSTRAINT hardship_request_id_check CHECK (hardship_request_id ~ '^HRS-2026-[0-9]{6}$'),
    CONSTRAINT hardship_request_account_fkey FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE RESTRICT,
    CONSTRAINT hardship_request_loan_fkey FOREIGN KEY (loan_id) REFERENCES loan (loan_id) ON DELETE RESTRICT,
    CONSTRAINT hardship_request_reason_enum CHECK (
        reason_code IN ('income_loss', 'medical', 'disaster', 'other')
    ),
    CONSTRAINT hardship_request_status_enum CHECK (status IN ('requested', 'approved', 'declined')),
    CONSTRAINT hardship_resolution_state CHECK ((status = 'requested') = (resolved_at IS NULL)),
    CONSTRAINT hardship_resolution_order CHECK (resolved_at IS NULL OR resolved_at >= requested_at)
);

CREATE TABLE collection_case (
    case_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    loan_id VARCHAR(32),
    status VARCHAR(16) NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,
    priority_score NUMERIC(5,2) NOT NULL,
    next_action_at TIMESTAMPTZ,
    CONSTRAINT collection_case_pkey PRIMARY KEY (case_id),
    CONSTRAINT collection_case_case_id_check CHECK (case_id ~ '^COL-2026-[0-9]{6}$'),
    CONSTRAINT collection_case_account_id_fkey FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE RESTRICT,
    CONSTRAINT collection_case_loan_id_fkey FOREIGN KEY (loan_id) REFERENCES loan (loan_id) ON DELETE RESTRICT,
    CONSTRAINT collection_case_status_enum CHECK (status IN ('open', 'paused', 'resolved', 'closed')),
    CONSTRAINT collection_case_priority_score_check CHECK (priority_score BETWEEN 0 AND 100),
    CONSTRAINT collection_case_close_order CHECK (closed_at IS NULL OR closed_at >= opened_at),
    CONSTRAINT collection_case_status_close_date CHECK ((status IN ('resolved', 'closed')) = (closed_at IS NOT NULL))
);

CREATE TABLE contact_attempt (
    contact_attempt_id VARCHAR(64) NOT NULL,
    case_id VARCHAR(32) NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL,
    channel VARCHAR(12) NOT NULL,
    outcome VARCHAR(20) NOT NULL,
    agent_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT contact_attempt_pkey PRIMARY KEY (contact_attempt_id),
    CONSTRAINT contact_attempt_contact_attempt_id_check CHECK (contact_attempt_id ~ '^CTP-COL-2026-[0-9]{6}-[0-9]{3}$'),
    CONSTRAINT contact_attempt_case_id_fkey FOREIGN KEY (case_id) REFERENCES collection_case (case_id) ON DELETE RESTRICT,
    CONSTRAINT contact_attempt_channel_enum CHECK (channel IN ('phone', 'email', 'sms', 'postal')),
    CONSTRAINT contact_attempt_outcome_enum CHECK (outcome IN ('connected', 'no_answer', 'voicemail', 'invalid_contact', 'refused', 'dispute_raised', 'policy_blocked'))
);

CREATE TABLE promise_to_pay (
    promise_id VARCHAR(64) NOT NULL,
    case_id VARCHAR(32) NOT NULL,
    promised_amount BIGINT NOT NULL,
    promised_date DATE NOT NULL,
    status VARCHAR(12) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    CONSTRAINT promise_to_pay_pkey PRIMARY KEY (promise_id),
    CONSTRAINT promise_to_pay_promise_id_check CHECK (promise_id ~ '^PTP-COL-2026-[0-9]{6}-[0-9]{3}$'),
    CONSTRAINT promise_to_pay_case_id_fkey FOREIGN KEY (case_id) REFERENCES collection_case (case_id) ON DELETE RESTRICT,
    CONSTRAINT promise_to_pay_promised_amount_check CHECK (promised_amount > 0),
    CONSTRAINT promise_to_pay_status_enum CHECK (status IN ('pending', 'kept', 'broken', 'cancelled')),
    CONSTRAINT promise_resolved_state CHECK ((status = 'pending') = (resolved_at IS NULL)),
    CONSTRAINT promise_resolved_order CHECK (resolved_at IS NULL OR resolved_at >= recorded_at)
);

CREATE TABLE payment (
    payment_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    posted_at TIMESTAMPTZ,
    amount BIGINT NOT NULL,
    unapplied_amount BIGINT NOT NULL,
    currency CHAR(3) NOT NULL,
    payment_method VARCHAR(16) NOT NULL,
    status VARCHAR(12) NOT NULL,
    external_reference VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT payment_pkey PRIMARY KEY (payment_id),
    CONSTRAINT payment_payment_id_check CHECK (payment_id ~ '^PMT-2026-[0-9]{6}$'),
    CONSTRAINT payment_account_id_fkey FOREIGN KEY (account_id) REFERENCES account (account_id) ON DELETE RESTRICT,
    CONSTRAINT payment_amount_check CHECK (amount > 0),
    CONSTRAINT payment_unapplied_amount_check CHECK (unapplied_amount BETWEEN 0 AND amount),
    CONSTRAINT payment_currency_check CHECK (currency ~ '^[A-Z]{3}$'),
    CONSTRAINT payment_payment_method_enum CHECK (payment_method IN ('bank_transfer', 'card', 'cash', 'direct_debit', 'other')),
    CONSTRAINT payment_status_enum CHECK (status IN ('pending', 'posted', 'returned', 'reversed')),
    CONSTRAINT payment_external_reference_check CHECK (external_reference IS NULL OR length(trim(external_reference)) > 0),
    CONSTRAINT payment_external_reference_key UNIQUE (external_reference),
    CONSTRAINT payment_posted_order CHECK (posted_at IS NULL OR posted_at >= received_at),
    CONSTRAINT payment_posted_state CHECK ((status = 'pending') = (posted_at IS NULL))
);

CREATE TABLE payment_allocation (
    payment_id VARCHAR(32) NOT NULL,
    installment_id VARCHAR(64) NOT NULL,
    allocated_amount BIGINT NOT NULL,
    allocated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT payment_allocation_pkey PRIMARY KEY (payment_id, installment_id),
    CONSTRAINT payment_allocation_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES payment (payment_id) ON DELETE RESTRICT,
    CONSTRAINT payment_allocation_installment_id_fkey FOREIGN KEY (installment_id) REFERENCES installment (installment_id) ON DELETE RESTRICT,
    CONSTRAINT payment_allocation_allocated_amount_check CHECK (allocated_amount > 0)
);

CREATE TABLE promise_reconciliation (
    promise_id VARCHAR(64) NOT NULL,
    payment_id VARCHAR(32) NOT NULL,
    reconciled_amount BIGINT NOT NULL,
    reconciled_at TIMESTAMPTZ NOT NULL,
    match_status VARCHAR(12) NOT NULL,
    CONSTRAINT promise_reconciliation_pkey PRIMARY KEY (promise_id, payment_id),
    CONSTRAINT promise_reconciliation_promise_fkey FOREIGN KEY (promise_id)
        REFERENCES promise_to_pay (promise_id) ON DELETE RESTRICT,
    CONSTRAINT promise_reconciliation_payment_fkey FOREIGN KEY (payment_id)
        REFERENCES payment (payment_id) ON DELETE RESTRICT,
    CONSTRAINT promise_reconciliation_amount_check CHECK (reconciled_amount > 0),
    CONSTRAINT promise_reconciliation_status_check
        CHECK (match_status IN ('matched', 'partial', 'excess'))
);

CREATE TABLE case_state_history (
    state_event_id VARCHAR(32) NOT NULL,
    case_id VARCHAR(32) NOT NULL,
    previous_status VARCHAR(16),
    new_status VARCHAR(16) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL,
    reason_code VARCHAR(40) NOT NULL,
    actor_type VARCHAR(24) NOT NULL,
    CONSTRAINT case_state_history_pkey PRIMARY KEY (state_event_id),
    CONSTRAINT case_state_history_id_check
        CHECK (state_event_id ~ '^CSH-[0-9]{6}$'),
    CONSTRAINT case_state_history_case_fkey FOREIGN KEY (case_id)
        REFERENCES collection_case (case_id) ON DELETE RESTRICT,
    CONSTRAINT case_state_history_previous_status_check
        CHECK (previous_status IS NULL OR previous_status IN ('open', 'paused', 'resolved', 'closed')),
    CONSTRAINT case_state_history_new_status_check
        CHECK (new_status IN ('open', 'paused', 'resolved', 'closed')),
    CONSTRAINT case_state_history_reason_check CHECK (length(trim(reason_code)) > 0),
    CONSTRAINT case_state_history_actor_check
        CHECK (actor_type IN ('system', 'operations_analyst', 'compliance_reviewer', 'administrator'))
);

CREATE TABLE decision_log (
    decision_id VARCHAR(32) NOT NULL,
    case_id VARCHAR(32),
    loan_id VARCHAR(32),
    rule_id VARCHAR(32) NOT NULL,
    decision_type VARCHAR(32) NOT NULL,
    outcome VARCHAR(16) NOT NULL,
    reason TEXT NOT NULL,
    priority_score NUMERIC(5,2),
    as_of_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT decision_log_pkey PRIMARY KEY (decision_id),
    CONSTRAINT decision_log_id_check CHECK (decision_id ~ '^DEC-2026-[0-9]{6}$'),
    CONSTRAINT decision_log_case_fkey FOREIGN KEY (case_id)
        REFERENCES collection_case (case_id) ON DELETE RESTRICT,
    CONSTRAINT decision_log_loan_fkey FOREIGN KEY (loan_id)
        REFERENCES loan (loan_id) ON DELETE RESTRICT,
    CONSTRAINT decision_log_rule_id_check CHECK (rule_id ~ '^R-[A-Z]+-[0-9]{2}$'),
    CONSTRAINT decision_log_type_check CHECK (
        decision_type IN (
            'prioritize', 'contact_allowed', 'contact_blocked',
            'route_to_review', 'close_paid_case', 'reconcile_promise'
        )
    ),
    CONSTRAINT decision_log_outcome_check
        CHECK (outcome IN ('allow', 'block', 'review', 'close', 'reconcile')),
    CONSTRAINT decision_log_reason_check CHECK (length(trim(reason)) > 0),
    CONSTRAINT decision_log_score_check
        CHECK (priority_score IS NULL OR priority_score BETWEEN 0 AND 100)
);

-- Explicit indexes cover every foreign-key column, including composite bridge keys.
CREATE INDEX account_customer_id_idx ON account (customer_id);
CREATE INDEX loan_account_id_idx ON loan (account_id);
CREATE INDEX installment_loan_id_idx ON installment (loan_id);
CREATE INDEX delinquency_snapshot_loan_id_idx ON delinquency_snapshot (loan_id);
CREATE INDEX contact_preference_account_id_idx ON contact_preference (account_id);
CREATE INDEX dispute_account_id_idx ON dispute (account_id);
CREATE INDEX dispute_loan_id_idx ON dispute (loan_id);
CREATE INDEX hardship_request_account_id_idx ON hardship_request (account_id);
CREATE INDEX hardship_request_loan_id_idx ON hardship_request (loan_id);
CREATE INDEX collection_case_account_id_idx ON collection_case (account_id);
CREATE INDEX collection_case_loan_id_idx ON collection_case (loan_id);
CREATE UNIQUE INDEX collection_case_one_open_per_loan_idx
    ON collection_case (loan_id) WHERE status = 'open' AND loan_id IS NOT NULL;
CREATE INDEX contact_attempt_case_id_idx ON contact_attempt (case_id);
CREATE INDEX promise_to_pay_case_id_idx ON promise_to_pay (case_id);
CREATE INDEX payment_account_id_idx ON payment (account_id);
CREATE INDEX payment_allocation_payment_id_idx ON payment_allocation (payment_id);
CREATE INDEX payment_allocation_installment_id_idx ON payment_allocation (installment_id);
CREATE INDEX promise_reconciliation_promise_id_idx
    ON promise_reconciliation (promise_id);
CREATE INDEX promise_reconciliation_payment_id_idx
    ON promise_reconciliation (payment_id);
CREATE INDEX case_state_history_case_id_idx ON case_state_history (case_id);
CREATE INDEX decision_log_case_id_idx ON decision_log (case_id);
CREATE INDEX decision_log_loan_id_idx ON decision_log (loan_id);
