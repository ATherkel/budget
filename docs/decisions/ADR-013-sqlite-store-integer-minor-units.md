# ADR-013: Store Data in SQLite, with Money as Integer Minor Units

**Status:** Proposed

## Context

The pipeline needs one local store for Bronze payloads and provenance, the
rebuildable Silver and Gold layers, and the publication and review state that
issues #8 and #10 define. The
[storage research for issue #9](../research/storage-and-operating-stack.md)
compared SQLite, DuckDB, PostgreSQL, and Parquet files queried with DuckDB
against the accepted contracts. The full original evidence is at commit
[`7c52d7f`](https://github.com/ATherkel/budget/blob/7c52d7f4b4b2c59bc68dd88416d48073e2773702/docs/research/storage-and-operating-stack.md).

Four facts decide it:

- The maintainer's deciding preference is low maintenance. The store runs
  unattended on one Windows machine at home.
- The read-only dashboard must keep reading while an import or rebuild writes.
  SQLite documents this directly: many readers and one writer, in separate
  processes on the same host, in WAL mode. DuckDB does not document one process
  writing a database file while another reads it.
- The Silver and Gold contracts type money as `Decimal`, and
  [ADR-006](ADR-006-balance-chain-reconciliation.md) and
  [ADR-010](ADR-010-quarantine-inconsistent-exports.md) compare stated balances
  exactly. A rounding error quarantines a correct export. SQLite has no exact
  decimal type, and `STRICT` tables forbid `NUMERIC` and `DECIMAL` outright.
- [ADR-003](ADR-003-immutable-transactions.md) makes Silver and Gold
  rebuildable, and [ADR-009](ADR-009-transaction-identity.md) derives
  transaction identity from content rather than storage. A later engine change
  is a rebuild from retained payloads and configuration, not a data migration.

Data access and migrations were a maintenance preference rather than an
evidence question. The maintainer chose the standard library over SQLAlchemy
and Alembic.

## Decision

- **Engine.** SQLite, through the standard library `sqlite3` module, with no
  ORM or query builder. Every process that opens a store runs on the same
  machine, and one process writes at a time.
- **Location.** The database path always comes from the active profile's
  configuration. No path is hard-coded in application code, migrations, or
  tests. The production database lives outside any cloud-synchronised folder.
  Its exact path, and the development and test paths, belong to issue #10.
- **Tables.** Every table is `STRICT`.
- **Connection settings.** The database uses WAL mode, set once when it is
  created, because the setting persists in the file. Every connection sets
  `foreign_keys = ON`, a `busy_timeout`, and `synchronous = FULL`, because
  SQLite resets these for each connection. The migrate command is the one
  exception; see Migrations.
- **Money.** Amounts and balances are stored as `INTEGER` counts of the
  currency's minor unit: DKK 12.34 is stored as `1234`. The number of decimal
  places comes from an ISO 4217 table in code, keyed by the account's
  configured currency, with DKK at two. A currency missing from the table is
  rejected. Conversion between `Decimal` and integer happens only at the
  persistence boundary and never passes through `float`. A value with more
  decimal places than its currency allows, or one outside SQLite's 64-bit
  integer range, is rejected rather than rounded or clamped. Every contract
  above storage keeps `Decimal`.
- **Migrations.** Numbered plain SQL files, applied in order by a small
  runner that records the schema version in `PRAGMA user_version`. Only an
  explicit migrate command creates or changes the schema. Opening a store
  never creates tables, and it fails when the database file does not exist.
  Each migration file and its `user_version` update run in one transaction,
  so a failure leaves the schema and the version as they were. The runner
  opens the transaction explicitly, because `executescript()` commits any
  open transaction and then runs in autocommit mode.
  The same runner and files serve every profile. Production takes a backup
  before migrating. A schema change confined to Silver or Gold may drop and
  rebuild those tables instead of altering them.
- **Foreign keys during migration.** The migrate command sets
  `foreign_keys = OFF` before it begins its transaction, runs
  `PRAGMA foreign_key_check` before committing, and fails the migration if
  that reports any row. With foreign keys on, the `DROP TABLE` in SQLite's
  table-rebuild procedure first deletes every row and fires
  `ON DELETE CASCADE`, which would delete child rows in Bronze. The setting
  cannot be changed inside a transaction, so it is set before one begins.
- **SQLite version floor.** The application refuses to open a store when
  `sqlite3.sqlite_version_info` is below 3.51.3, the first release with
  SQLite's fix for the
  [WAL-reset bug](https://www.sqlite.org/wal.html#walresetbug). The bug
  affects WAL databases where separate processes write or checkpoint at the
  same instant, which a dashboard reading during an import can cause. The
  interpreter comes from uv's managed Python builds, not the operating system:
  the repository pins the version in `.python-version`, and
  `python-preference = "only-managed"` in `pyproject.toml` stops uv from
  choosing a system interpreter on the household machine or in CI.
- **Backups.** A backup uses SQLite's backup API or `VACUUM INTO`, never a
  file copy of a live database. Raw exports keep their separate archive, and
  the store holds a second copy of each payload's exact bytes.

## Consequences

- No database server is installed, configured, or upgraded, and the runtime
  gains no third-party dependency.
- `Decimal` stays the only money type in the Silver and Gold contracts and in
  analytics. SQL sums of integer minor units are exact, and the persistence
  layer carries the conversion rules, with tests on both sides of every limit.
- `STRICT INTEGER` checks the storage type, not the unit. Whether a stored
  integer means øre is enforced only by the conversion boundary and its tests.
- Some `ALTER TABLE` changes need a table rebuild. That is a cost for Bronze
  and the retained inputs, and negligible for the derived layers.
- WAL alone does not give a report one consistent Gold publication. Issue #8
  still has to define how a build is published and selected.
- SQLite also backported the WAL-reset fix to 3.44.6 and 3.50.7. A plain
  version comparison refuses those, which is deliberate: the managed builds
  are well above the floor (CPython 3.12.14 and 3.14.7 from September 2026
  bundle SQLite 3.53.1), and one comparison is simpler than a list of
  backports.
- A system Python no longer satisfies the project. The python.org 3.12.3 on
  the household machine bundles SQLite 3.45.1, below the floor.
- Querying the store through DuckDB as a read-only analytics engine is
  deferred, not rejected.
- Resolves the storage part of
  [issue #10](https://github.com/ATherkel/budget/issues/10), using the evidence
  from [issue #9](https://github.com/ATherkel/budget/issues/9), once accepted.
