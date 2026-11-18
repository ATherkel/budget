-- Copyright 2026 Therkel
-- Gold schema version 2: every account has an owner from the household's
-- declared owners (ADR-021), and each publication records those owners in
-- their display order, counting from 1.

ALTER TABLE accounts ADD COLUMN owner_id TEXT;

CREATE TABLE owners (
    publication_id INTEGER NOT NULL REFERENCES results (publication_id),
    owner_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    display_order INTEGER NOT NULL CHECK (display_order >= 1),
    PRIMARY KEY (publication_id, owner_id),
    UNIQUE (publication_id, display_order)
) STRICT;
