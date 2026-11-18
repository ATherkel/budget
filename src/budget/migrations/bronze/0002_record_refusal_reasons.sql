-- Copyright 2026 Therkel
-- Bronze schema version 2: a refused import run records why. One row per rule
-- the run broke; `stored` and `repeat` runs have none. The codes name rules
-- only, so a row holds no date, amount, account number or file name.

CREATE TABLE import_run_refusals (
    import_run_id TEXT NOT NULL REFERENCES import_runs(import_run_id),
    code TEXT NOT NULL,
    PRIMARY KEY (import_run_id, code)
) STRICT;
