-- Copyright 2026 Therkel
-- Gold store, schema version 1: the publications of one profile
-- (publications.md, ADR-014), with the one-row identity that records which
-- profile and stage own this file.
--
-- A publication's metadata is kept forever. Its result is retained while a row
-- in `results` names it; every result table is keyed by `publication_id`
-- first, so no read can cross publications. The pointer is the last row of
-- `pointer_moves`, which is append-only.

CREATE TABLE store_identity (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    profile TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage = 'gold')
) STRICT;

CREATE TABLE publications (
    publication_id INTEGER PRIMARY KEY CHECK (publication_id >= 1),
    kind TEXT NOT NULL CHECK (kind IN ('pipeline', 'as_known_at')),
    label TEXT,
    known_at TEXT NOT NULL,
    built_at TEXT NOT NULL,
    replayed_at TEXT,
    contract_version TEXT NOT NULL,
    fingerprint_scheme TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL
) STRICT;

-- One row per publication whose result the store still holds.
CREATE TABLE results (
    publication_id INTEGER PRIMARY KEY REFERENCES publications (publication_id)
) STRICT;

CREATE TABLE pointer_moves (
    move INTEGER PRIMARY KEY,
    moved_at TEXT NOT NULL,
    from_publication_id INTEGER REFERENCES publications (publication_id),
    to_publication_id INTEGER NOT NULL REFERENCES publications (publication_id),
    cause TEXT NOT NULL CHECK (cause IN ('build', 'undo', 'migration'))
) STRICT;
