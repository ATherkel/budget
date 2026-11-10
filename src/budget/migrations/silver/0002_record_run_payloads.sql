-- Copyright 2026 Therkel
-- Silver schema version 2: each import run result and each evidence export
-- records the payload it was built from, so Gold's recipe can name the runs
-- Silver consumed without reading Bronze.
--
-- Version 1 did not record the payload and Silver is derived from Bronze, so
-- what version 1 derived is cleared (children first) and the store reads as
-- never built until `budget rebuild --from silver` fills it again.
--
-- Version 1, as v0.2.0 shipped it, had no evidence exports, so the table
-- starts here.

DELETE FROM review_item_payloads;
DELETE FROM review_items;
DELETE FROM import_run_result_review_items;
DELETE FROM validation_errors;
DELETE FROM import_run_results;
DELETE FROM account_evidence;
DELETE FROM balance_observations;
DELETE FROM unbooked_records;
DELETE FROM transaction_evidence;
DELETE FROM transactions;
DELETE FROM account_currencies;

-- Each import run counted in an account's evidence, with its export date and
-- declared range, so Gold can settle late bookings without reading Bronze.
CREATE TABLE evidence_exports (
    ordinal INTEGER PRIMARY KEY,
    import_run_id TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    exported_on TEXT NOT NULL,
    covers_from TEXT NOT NULL,
    covers_through TEXT NOT NULL
) STRICT;

ALTER TABLE evidence_exports ADD COLUMN payload_id TEXT NOT NULL DEFAULT '';
ALTER TABLE import_run_results ADD COLUMN payload_id TEXT NOT NULL DEFAULT '';
