# Storage for the household budget

Research for [#9](https://github.com/ATherkel/budget/issues/9), simplified and reviewed on 2026-09-19. **Recommendation: SQLite.** The final choice and operating instructions belong to [#10](https://github.com/ATherkel/budget/issues/10).

## What the recommendation means

Keep the working database on this computer, outside OneDrive. Store money as whole øre: DKK 12.34 becomes `1234`. Convert it to Python `Decimal` when returning financial records to the application.

Use `STRICT` tables to enforce column types and WAL mode to let the dashboard read while an import or rebuild writes. All database processes must run on the same computer, with one writer at a time. Require SQLite 3.51.3 or later, or a release with the documented WAL-reset fix. The original research measured SQLite 3.45.1, which predates that fix. [SQLite WAL documentation](https://www.sqlite.org/wal.html).

Keep the original exports in their separate archive and retain a second copy of their exact bytes in the database. Keeping the live database outside cloud sync is a precaution against inconsistent copies of an open database and its journal files. [SQLite corruption guidance](https://www.sqlite.org/howtocorrupt.html).

## Why SQLite

The deciding preference is low maintenance. Python already includes a SQLite interface, so no database server needs to run. The reported household dataset is small; this review did not independently remeasure private imports.

| Option | Main benefit | Main cost |
| --- | --- | --- |
| **SQLite with integer øre** | Simple local setup; concurrent readers and one writer | We must implement and test money conversion; some schema changes require rebuilding tables |
| DuckDB | Useful analytical SQL and a decimal type | Separate processes cannot directly read and write the same native database file concurrently in embedded mode |
| PostgreSQL | Native exact decimals and server-managed concurrent access | Another service to configure, back up, and upgrade |
| Parquet files queried with DuckDB | Suitable for immutable reporting files | We must manage complete versions, publication selection, and cleanup ourselves |

DuckDB's restriction concerns access to the **same database file**. It does not rule out building a separate version while readers use the old one. Likewise, a Parquet design could publish new directories without changing files readers are using. These are possible alternatives requiring more application code; their publication behavior still needs validation in [#8](https://github.com/ATherkel/budget/issues/8). [DuckDB concurrency](https://duckdb.org/docs/current/connect/concurrency), [Parquet queries](https://duckdb.org/docs/current/data/parquet/overview).

PostgreSQL remains viable if operating a server is acceptable. Its `numeric` type and psycopg's `Decimal` conversion support exact money. [PostgreSQL numeric types](https://www.postgresql.org/docs/current/datatype-numeric.html), [psycopg adaptation](https://www.psycopg.org/psycopg3/docs/advanced/adapt.html).

## What we must get right

- **Money conversion:** reject unsupported precision and out-of-range amounts. Do not pass through floating point. `STRICT INTEGER` checks storage type, not whether a number means kroner or øre; it also accepts values it can convert losslessly. Text can preserve decimal values too, but integer units make SQL sums straightforward. [SQLite STRICT tables](https://www.sqlite.org/stricttables.html).
- **Recovery:** retain exports, import declarations, account/category configuration, classification rules, and manual decisions. Stable transaction IDs let retained decisions find their transactions again; IDs cannot recreate lost decisions. Preserve required historical publications too. These requirements follow the repository's [Silver contract](https://github.com/ATherkel/budget/blob/main/docs/architecture/silver-layer.md) and [#10](https://github.com/ATherkel/budget/issues/10).
- **Consistent reports:** each report must use one complete Gold publication. WAL alone does not define that application-level rule. [Gold contract](https://github.com/ATherkel/budget/blob/main/docs/architecture/gold-contract.md).
- **Import dates:** preserve the filename, which may supply `exported_on` (when the bank created the export). `covers_through` means how far the requested history extends and follows separate declaration rules. [Bronze contract](https://github.com/ATherkel/budget/blob/main/docs/architecture/bronze-layer.md).

## Decisions still needed

[#10](https://github.com/ATherkel/budget/issues/10) must record the accepted stack, database location, currency scale, migration tools, dashboard authentication, and a tested recovery procedure. [#8](https://github.com/ATherkel/budget/issues/8) defines publication and retained history.

Before adding an API import, verify that its dates, descriptions, and repeated transactions map consistently to CSV imports. An API-provided ID alone does **not** change the current hash: [ADR-009](https://github.com/ATherkel/budget/blob/main/docs/decisions/ADR-009-transaction-identity.md) does not include it. Compatibility is an open verification task, not a demonstrated failure.

This is a storage recommendation. The existing FastAPI/Jinja/HTMX/Plotly direction remains provisional; deployment, startup, authentication, and recovery commands still need to be specified.

🤖 Generated with Codex (GPT-6)
