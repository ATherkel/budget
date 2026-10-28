-- Copyright 2026 Therkel
-- Gold schema version 5: each new recipe retains the exact Silver build it
-- consumed. Historical recipes remain readable with unknown Silver
-- provenance; nothing is inferred from today's Silver store or decision log.

ALTER TABLE recipes ADD COLUMN silver_fingerprint_scheme TEXT;
ALTER TABLE recipes ADD COLUMN silver_result_fingerprint TEXT;
ALTER TABLE recipes ADD COLUMN silver_code_version TEXT;
ALTER TABLE recipes ADD COLUMN silver_decision_log_position INTEGER
    CHECK (
        silver_decision_log_position IS NULL
        OR silver_decision_log_position >= 0
    );
ALTER TABLE recipes ADD COLUMN silver_decision_log_prefix_sha256 TEXT;
ALTER TABLE recipes ADD COLUMN silver_bronze_parser_provenance TEXT;

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
