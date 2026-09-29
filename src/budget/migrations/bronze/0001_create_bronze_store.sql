-- Copyright 2026 Therkel
-- Bronze store, schema version 1: raw payloads, their import runs, the source
-- records and format failures derived from them, and the one-row identity that
-- records which profile and stage own this file.

CREATE TABLE raw_payloads (
    payload_id TEXT PRIMARY KEY,
    byte_length INTEGER NOT NULL,
    content BLOB NOT NULL
) STRICT;

CREATE TABLE import_runs (
    import_run_id TEXT PRIMARY KEY,
    payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
    declared_account_id TEXT NOT NULL,
    source_format TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    exported_on TEXT NOT NULL,
    exported_on_source TEXT NOT NULL,
    covers_through TEXT NOT NULL,
    covers_through_source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    repeat_of TEXT REFERENCES import_runs(import_run_id)
) STRICT;

CREATE TABLE source_records (
    payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
    record_ordinal INTEGER NOT NULL,
    fields TEXT NOT NULL,
    PRIMARY KEY (payload_id, record_ordinal)
) STRICT;

CREATE TABLE format_failures (
    payload_id TEXT NOT NULL REFERENCES raw_payloads(payload_id),
    source_format TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (payload_id, source_format)
) STRICT;

CREATE TABLE store_identity (
    profile TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage = 'bronze')
) STRICT;
