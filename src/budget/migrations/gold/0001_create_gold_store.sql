-- Copyright 2026 Therkel
-- Gold store, schema version 1: the publications of one profile
-- (publications.md, ADR-014), with the one-row identity that records which
-- profile and stage own this file.
--
-- A publication's metadata is kept forever. Its result is retained while a row
-- in `results` names it; every result table is keyed by `publication_id`
-- first, so no read can cross publications. The pointer is the last row of
-- `pointer_moves`, which is append-only.

CREATE TABLE store_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    profile TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage = 'gold')
) STRICT;

CREATE TABLE publications (
    publication_id INTEGER PRIMARY KEY CHECK (publication_id >= 1),
    kind TEXT NOT NULL CHECK (kind IN ('pipeline', 'as_known_at')),
    label TEXT CHECK (label IS NULL OR trim(label) <> ''),
    known_at TEXT NOT NULL,
    built_at TEXT NOT NULL,
    replayed_at TEXT,
    contract_version TEXT NOT NULL,
    fingerprint_scheme TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL
) STRICT;

-- A recipe, kept forever, names its inputs (publications.md, *The Recipe*).
-- Each distinct configuration is stored once, as the canonical text its
-- fingerprint hashes.
CREATE TABLE configuration_snapshots (
    fingerprint TEXT PRIMARY KEY,
    content TEXT NOT NULL
) STRICT;

CREATE TABLE recipes (
    publication_id INTEGER PRIMARY KEY REFERENCES publications (publication_id),
    configuration_fingerprint TEXT NOT NULL
        REFERENCES configuration_snapshots (fingerprint),
    decision_log_position INTEGER NOT NULL CHECK (decision_log_position >= 0),
    decision_log_prefix_sha256 TEXT NOT NULL,
    code_version TEXT,
    contract_version TEXT NOT NULL,
    silver_identity_version TEXT NOT NULL,
    python_version TEXT NOT NULL,
    sqlite_version TEXT NOT NULL,
    -- The late-booking window the build used: `[gold] late_booking_days`,
    -- whose default is 7 days.
    late_booking_days INTEGER NOT NULL DEFAULT 7
        CHECK (late_booking_days >= 0),
    -- The exact Silver build the recipe consumed (#373).
    silver_fingerprint_scheme TEXT,
    silver_result_fingerprint TEXT,
    silver_code_version TEXT,
    silver_decision_log_position INTEGER
        CHECK (
            silver_decision_log_position IS NULL
            OR silver_decision_log_position >= 0
        ),
    silver_decision_log_prefix_sha256 TEXT,
    silver_bronze_parser_provenance TEXT
) STRICT;

-- Each import run the recipe consumed, with the account the run declared
-- (#476).
CREATE TABLE recipe_import_runs (
    publication_id INTEGER NOT NULL REFERENCES recipes (publication_id),
    import_run_id TEXT NOT NULL,
    payload_id TEXT NOT NULL,
    account_id TEXT,
    PRIMARY KEY (publication_id, import_run_id)
) STRICT;

CREATE TABLE recipe_silver_currencies (
    publication_id INTEGER NOT NULL REFERENCES recipes (publication_id),
    account_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    PRIMARY KEY (publication_id, account_id)
) STRICT;

CREATE TABLE recipe_silver_decisions (
    publication_id INTEGER NOT NULL REFERENCES recipes (publication_id),
    ordinal INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN (
            'accept-discrepancy',
            'same-transaction',
            'void-import-run',
            'withdrawn'
        )
    ),
    decision_id TEXT NOT NULL,
    target TEXT NOT NULL,
    payload_id TEXT,
    record_ordinal INTEGER,
    PRIMARY KEY (publication_id, ordinal),
    CHECK (
        (
            kind IN ('accept-discrepancy', 'void-import-run', 'withdrawn')
            AND payload_id IS NULL
            AND record_ordinal IS NULL
        )
        OR
        (
            kind = 'same-transaction'
            AND payload_id IS NOT NULL
            AND record_ordinal >= 0
        )
    )
) STRICT;

-- One row per publication whose result the store still holds.
CREATE TABLE results (
    publication_id INTEGER PRIMARY KEY REFERENCES publications (publication_id)
) STRICT;

CREATE TABLE pointer_moves (
    move INTEGER PRIMARY KEY,
    moved_at TEXT NOT NULL,
    from_publication_id INTEGER REFERENCES publications (publication_id),
    to_publication_id INTEGER NOT NULL REFERENCES publications (publication_id),
    cause TEXT NOT NULL CHECK (cause IN ('build', 'undo', 'migration'))
) STRICT;

-- Where a restore's recovered publication history ends (`publications.md`,
-- *Publication recovery*; #121). `restore` brings back the publications a
-- backup set holds; any made after the set are lost. Each restore records one
-- row. Publications from `first_publication_id` on were built after it.
CREATE TABLE recovery_boundaries (
    boundary INTEGER PRIMARY KEY,
    backup_set TEXT NOT NULL,
    backup_created_at TEXT NOT NULL,
    restored_at TEXT NOT NULL,
    restored_current_id INTEGER REFERENCES publications (publication_id),
    first_publication_id INTEGER NOT NULL CHECK (first_publication_id >= 1)
) STRICT;

-- The result tables. Money is INTEGER minor units of the account's currency
-- (ADR-013), dates are ISO 8601 text, and a month is `YYYY-MM`. Every key
-- leads with `publication_id`, and every reference stays inside one
-- publication.

CREATE TABLE accounts (
    publication_id INTEGER NOT NULL REFERENCES results (publication_id),
    account_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('current', 'savings')),
    ownership_scope TEXT NOT NULL
        CHECK (ownership_scope IN ('household', 'person')),
    currency TEXT NOT NULL,
    closed_on TEXT,
    coverage_start TEXT,
    evidence_through TEXT,
    PRIMARY KEY (publication_id, account_id)
) STRICT;

CREATE TABLE categories (
    publication_id INTEGER NOT NULL REFERENCES results (publication_id),
    category_id TEXT NOT NULL,
    name TEXT NOT NULL,
    group_id TEXT NOT NULL,
    group_name TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('income', 'expense')),
    PRIMARY KEY (publication_id, category_id)
) STRICT;

CREATE TABLE transactions (
    publication_id INTEGER NOT NULL,
    transaction_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    account_sequence INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    description TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (
        transaction_type IN (
            'income', 'expense', 'refund', 'transfer', 'adjustment', 'unknown'
        )
    ),
    transfer_group_id TEXT,
    balance_after INTEGER,
    balance_check TEXT NOT NULL CHECK (
        balance_check IN ('opening', 'consistent', 'break', 'missing_balance')
    ),
    PRIMARY KEY (publication_id, transaction_id),
    -- The target of an allocation's reference, so the two agree on account
    -- and date (gold-contract.md, invariant 6).
    UNIQUE (publication_id, transaction_id, account_id, transaction_date),
    FOREIGN KEY (publication_id, account_id)
        REFERENCES accounts (publication_id, account_id)
) STRICT;

CREATE TABLE category_allocations (
    publication_id INTEGER NOT NULL,
    allocation_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    category_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    PRIMARY KEY (publication_id, allocation_id),
    FOREIGN KEY (publication_id, transaction_id, account_id, transaction_date)
        REFERENCES transactions
            (publication_id, transaction_id, account_id, transaction_date),
    FOREIGN KEY (publication_id, account_id)
        REFERENCES accounts (publication_id, account_id),
    FOREIGN KEY (publication_id, category_id)
        REFERENCES categories (publication_id, category_id)
) STRICT;

CREATE TABLE monthly_balances (
    publication_id INTEGER NOT NULL,
    account_id TEXT NOT NULL,
    month TEXT NOT NULL,
    opening_balance INTEGER,
    closing_balance INTEGER,
    coverage TEXT NOT NULL CHECK (coverage IN ('complete', 'partial', 'no_data')),
    late_bookings_settled INTEGER NOT NULL CHECK (late_bookings_settled IN (0, 1)),
    PRIMARY KEY (publication_id, account_id, month),
    FOREIGN KEY (publication_id, account_id)
        REFERENCES accounts (publication_id, account_id)
) STRICT;

-- Classification questions published with their build. A review item and
-- both identifier lists belong to one retained result. Child ordinals
-- preserve the order Gold derived, including transaction targets that are
-- absent from the publication.

CREATE TABLE classification_review_items (
    publication_id INTEGER NOT NULL REFERENCES results (publication_id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    review_item_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN (
            'unclassified',
            'rule-conflict',
            'sign-mismatch',
            'ambiguous-transfer',
            'unmatched-transfer',
            'decision-not-applicable'
        )
    ),
    decision_id TEXT,
    reason TEXT,
    PRIMARY KEY (publication_id, review_item_id),
    UNIQUE (publication_id, ordinal)
) STRICT;

-- A target's account, date, amount and description belong to the published
-- transaction. The bank's label exists only in Silver lineage, so it is kept
-- beside the review target that needs it.
CREATE TABLE classification_review_targets (
    publication_id INTEGER NOT NULL,
    review_item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    transaction_id TEXT NOT NULL,
    bank_category TEXT,
    PRIMARY KEY (publication_id, review_item_id, ordinal),
    UNIQUE (publication_id, review_item_id, transaction_id),
    FOREIGN KEY (publication_id, review_item_id)
        REFERENCES classification_review_items (publication_id, review_item_id)
) STRICT;

CREATE TABLE classification_review_rules (
    publication_id INTEGER NOT NULL,
    review_item_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    rule_id TEXT NOT NULL,
    PRIMARY KEY (publication_id, review_item_id, ordinal),
    UNIQUE (publication_id, review_item_id, rule_id),
    FOREIGN KEY (publication_id, review_item_id)
        REFERENCES classification_review_items (publication_id, review_item_id)
) STRICT;
