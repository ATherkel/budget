-- Copyright 2026 Therkel
-- Silver store, schema version 2: each import run's result names the account
-- the run declared, so a reader can trace a quarantined run to its account
-- without a join through Bronze, which a stored view cannot make across files.
--
-- A migration cannot read the account from Bronze, so it does not backfill.
-- It empties the whole persisted result instead, and Silver reads as "not
-- built yet" until the next `budget rebuild` repopulates it. Emptying only
-- `import_run_results` would leave review items and transactions whose runs
-- no longer exist, so `budget review` could not name the run that raised an
-- item. Child tables go first, so no cascading delete touches a row twice.

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

-- SQLite requires a default to add a NOT NULL column. The empty default is
-- never a valid value: the CHECK refuses it, so every row must name an account.
ALTER TABLE import_run_results
    ADD COLUMN account_id TEXT NOT NULL DEFAULT '' CHECK (account_id <> '');
