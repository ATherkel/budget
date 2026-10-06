-- Copyright 2026 Therkel
-- Silver store, schema version 1: the persisted result of one Silver build,
-- plus the account currency snapshot the result's amounts were written under
-- and the one-row identity that records which profile and stage own this file.
--
-- Every table below `store_identity` is derived: a replacement clears all of
-- them and rewrites them in one transaction, so a reader always sees one whole
-- SilverResult and never a mixture of two builds.

CREATE TABLE store_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    profile TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage = 'silver')
) STRICT;

-- The account currency snapshot: unbooked amounts and balance observations
-- carry integer minor units, so their currency must be stored alongside them
-- rather than re-read from mutable configuration.
CREATE TABLE account_currencies (
    account_id TEXT PRIMARY KEY,
    currency TEXT NOT NULL
) STRICT;

CREATE TABLE transactions (
    ordinal INTEGER PRIMARY KEY,
    transaction_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    description TEXT NOT NULL,
    source_system TEXT NOT NULL,
    balance INTEGER,
    source_status TEXT NOT NULL,
    booking_status TEXT NOT NULL
        CHECK (booking_status IN ('booked', 'pending', 'cancelled')),
    occurrence INTEGER NOT NULL,
    day_sequence INTEGER NOT NULL,
    identity_version TEXT NOT NULL,
    bank_category TEXT,
    bank_subcategory TEXT
) STRICT;

CREATE TABLE transaction_evidence (
    ordinal INTEGER PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
    payload_id TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    import_run_id TEXT NOT NULL
) STRICT;

CREATE TABLE unbooked_records (
    ordinal INTEGER PRIMARY KEY,
    payload_id TEXT NOT NULL,
    record_ordinal INTEGER NOT NULL,
    import_run_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    amount INTEGER NOT NULL,
    source_status TEXT NOT NULL,
    booking_status TEXT NOT NULL
        CHECK (booking_status IN ('booked', 'pending', 'cancelled'))
) STRICT;

CREATE TABLE balance_observations (
    ordinal INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    balance_date TEXT NOT NULL,
    end_of_day_balance INTEGER,
    payload_id TEXT NOT NULL
) STRICT;

CREATE TABLE account_evidence (
    ordinal INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    covers_from TEXT NOT NULL,
    covers_through TEXT NOT NULL
) STRICT;

CREATE TABLE import_run_results (
    ordinal INTEGER PRIMARY KEY,
    import_run_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('accepted', 'quarantined')),
    covered_from TEXT NOT NULL,
    covered_to TEXT NOT NULL
) STRICT;

CREATE TABLE validation_errors (
    import_run_ordinal INTEGER NOT NULL
        REFERENCES import_run_results(ordinal) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    payload_id TEXT NOT NULL,
    record_ordinal INTEGER,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    PRIMARY KEY (import_run_ordinal, position)
) STRICT;

CREATE TABLE import_run_result_review_items (
    import_run_ordinal INTEGER NOT NULL
        REFERENCES import_run_results(ordinal) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    review_item_id TEXT NOT NULL,
    PRIMARY KEY (import_run_ordinal, position)
) STRICT;

CREATE TABLE review_items (
    ordinal INTEGER PRIMARY KEY,
    review_item_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL
        CHECK (kind IN ('export-disagreement', 'dropped-transaction', 'balance-break')),
    account_id TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    resolved_by TEXT,
    -- No foreign key: a review item stands for a transaction the bank dropped,
    -- and a *withdrawn* decision can remove that transaction from the build.
    transaction_id TEXT
) STRICT;

CREATE TABLE review_item_payloads (
    review_item_ordinal INTEGER NOT NULL
        REFERENCES review_items(ordinal) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    payload_id TEXT NOT NULL,
    PRIMARY KEY (review_item_ordinal, position)
) STRICT;
