-- Copyright 2026 Therkel
-- Gold schema version 3: bank category provenance for review targets.
--
-- A target's account, date, amount and description already belong to the
-- published transaction. The bank's label exists only in Silver lineage, so
-- retain it beside the review target that needs it. Existing publications get
-- null: an absent historic label is unavailable, never reconstructed from a
-- newer Silver result.

ALTER TABLE classification_review_targets ADD COLUMN bank_category TEXT;
