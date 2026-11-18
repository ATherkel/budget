-- Copyright 2026 Therkel
-- Bronze schema version 2: a refused import run records why. One row per rule
-- the run broke; `stored` and `repeat` runs have none. The codes name rules
-- only, so a row holds no date, amount, account number or file name.
--
-- Version 1 recorded no reasons, so every run it already refused gets the
-- single code `legacy-unrecorded` rather than a guess at which rule applied.

CREATE TABLE import_run_refusals (
    import_run_id TEXT NOT NULL REFERENCES import_runs(import_run_id),
    code TEXT NOT NULL,
    PRIMARY KEY (import_run_id, code)
) STRICT;

INSERT INTO import_run_refusals (import_run_id, code)
SELECT import_run_id, 'legacy-unrecorded' FROM import_runs WHERE outcome = 'refused';
