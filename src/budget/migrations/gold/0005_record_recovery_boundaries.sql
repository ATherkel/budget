-- Copyright 2026 Therkel
-- Gold schema version 5: where a restore's recovered publication history ends
-- (`publications.md`, *Publication recovery*; #121).
--
-- `restore` brings back the publications a backup set holds; any made after
-- the set are lost. Each restore records one row. Publications from
-- `first_publication_id` on were built after it.

CREATE TABLE recovery_boundaries (
    boundary INTEGER PRIMARY KEY,
    backup_set TEXT NOT NULL,
    backup_created_at TEXT NOT NULL,
    restored_at TEXT NOT NULL,
    restored_current_id INTEGER REFERENCES publications (publication_id),
    first_publication_id INTEGER NOT NULL CHECK (first_publication_id >= 1)
) STRICT;
