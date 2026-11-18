-- Copyright 2026 Therkel
-- Gold schema version 2: every account has an owner from the household's
-- declared owners (ADR-021), which replaces its ownership scope, and each
-- publication records those owners in their display order, counting from 1.
--
-- Version 1 recorded no owner, and its ownership scope cannot say which
-- member owns a `person` account, so every account it already published gets
-- the owner `legacy-unrecorded` rather than a guess. The next Gold rebuild
-- publishes the declared owners.

ALTER TABLE accounts ADD COLUMN owner_id TEXT;

UPDATE accounts SET owner_id = 'legacy-unrecorded';

ALTER TABLE accounts DROP COLUMN ownership_scope;

CREATE TABLE owners (
    publication_id INTEGER NOT NULL REFERENCES results (publication_id),
    owner_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    display_order INTEGER NOT NULL CHECK (display_order >= 1),
    PRIMARY KEY (publication_id, owner_id),
    UNIQUE (publication_id, display_order)
) STRICT;
