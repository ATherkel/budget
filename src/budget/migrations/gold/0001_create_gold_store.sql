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
    label TEXT,
    known_at TEXT NOT NULL,
    built_at TEXT NOT NULL,
    replayed_at TEXT,
    contract_version TEXT NOT NULL,
    fingerprint_scheme TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL
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
    FOREIGN KEY (publication_id, transaction_id)
        REFERENCES transactions (publication_id, transaction_id),
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
