-- Copyright 2026 Therkel
-- Gold schema version 7: a recipe keeps the account each consumed import run
-- declared (#476).
--
-- Rows written before this migration keep NULL: their account was not stored
-- and is not backfilled from Bronze or a later Silver result.

ALTER TABLE recipe_import_runs ADD COLUMN account_id TEXT;
