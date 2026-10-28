-- Copyright 2026 Therkel
-- Silver schema version 3: complete results commit with the inputs and producer
-- identity that made them.
--
-- Earlier builds did not record which runs, currencies, decisions or code they
-- consumed. Silver's result is derived, so those rows are cleared rather than
-- assigned today's context. A later rebuild fills an explicit completion row.

DELETE FROM review_item_payloads;
DELETE FROM review_items;
DELETE FROM import_run_result_review_items;
DELETE FROM validation_errors;
DELETE FROM import_run_results;
DELETE FROM evidence_exports;
DELETE FROM account_evidence;
DELETE FROM balance_observations;
DELETE FROM unbooked_records;
DELETE FROM transaction_evidence;
DELETE FROM transactions;
DELETE FROM account_currencies;

-- Present after every replacement, including a successful empty or an
-- explicitly unknown direct replacement. Its absence means never built.
CREATE TABLE silver_builds (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    provenance_state TEXT NOT NULL CHECK (provenance_state IN ('known', 'unknown')),
    fingerprint_scheme TEXT,
    result_fingerprint TEXT,
    code_version TEXT,
    identity_version TEXT,
    decision_log_position INTEGER,
    decision_log_prefix_sha256 TEXT,
    bronze_parser_provenance TEXT,
    CHECK (
        (
            provenance_state = 'unknown'
            AND fingerprint_scheme IS NULL
            AND result_fingerprint IS NULL
            AND code_version IS NULL
            AND identity_version IS NULL
            AND decision_log_position IS NULL
            AND decision_log_prefix_sha256 IS NULL
            AND bronze_parser_provenance IS NULL
        )
        OR
        (
            provenance_state = 'known'
            AND fingerprint_scheme IS NOT NULL
            AND result_fingerprint IS NOT NULL
            AND identity_version IS NOT NULL
            AND decision_log_position >= 0
            AND decision_log_prefix_sha256 IS NOT NULL
            AND bronze_parser_provenance = 'unknown'
        )
    )
) STRICT;

CREATE TABLE silver_build_runs (
    import_run_id TEXT PRIMARY KEY,
    payload_id TEXT NOT NULL
) STRICT;

CREATE TABLE silver_build_currencies (
    account_id TEXT PRIMARY KEY,
    currency TEXT NOT NULL
) STRICT;

-- One row per effective Silver decision. `kind` fixes which optional columns
-- carry its exact typed fields.
CREATE TABLE silver_build_decisions (
    ordinal INTEGER PRIMARY KEY,
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
