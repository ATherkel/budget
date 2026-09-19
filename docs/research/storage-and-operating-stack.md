# Storage and the local operating stack

Research date: 2026-09-19. Resolves the investigation in
[Choose storage and the local operating stack](https://github.com/ATherkel/budget/issues/9).
This is research evidence and a recommendation, not the decision. The stack decision
belongs to [issue #10](https://github.com/ATherkel/budget/issues/10).

No private financial data was inspected or included; `imports/` was measured in
aggregate only — file counts, row counts, and the span of transaction dates.

Evidence is official project documentation and format specifications. Two claims rest
on measurements taken on the maintainer's own machine because no primary source states
them; both are labelled `measured` where they appear, and every unverified claim is
listed under [Gaps in the evidence](#gaps-in-the-evidence).

## Finding and project context

**Recommendation: SQLite, with monetary amounts stored as `INTEGER` counts of the
currency's minor unit (øre), in `STRICT` tables, in WAL mode, with the database file
outside any cloud-synchronised folder.** The raw bank exports remain the system of
record in their own OneDrive folder, and the database holds a second copy of each
payload for cross-checking.

This is not the option with the best feature list. PostgreSQL has exact decimals end to
end, native authentication, and the strongest migration story. It is the option with the
fewest things that can go wrong while unattended, and the requirement that actually
discriminated between the candidates was not decimals, dimensional SQL, or migrations —
all four candidates handle those — but **concurrency**, where two of the four are ruled
out by their own documentation.

The decision is also cheaper than it looks. [ADR-003](../decisions/ADR-003-immutable-transactions.md)
makes the payload the immutable record and declares "Silver and Gold are rebuildable
derived data", and [`silver-layer.md`](../architecture/silver-layer.md) guarantees a
rebuild reproduces identical output "including identifiers". Changing engine later is a
*rebuild into the new engine*, not a data migration, and because
[ADR-009](../decisions/ADR-009-transaction-identity.md) derives identity from content
rather than from storage, manual decisions and classifications reattach to the same
transactions afterwards. Nothing has to be carried across. That argues for choosing what
is cheapest to live with rather than what is most future-proof.

## What the accepted contracts already require

These are not preferences to be traded off. They are accepted decisions on `main` as of
2026-09-19, and a candidate that cannot meet them is out.

**Money is `decimal.Decimal` and must round-trip unchanged.**
[`gold-contract.md`](../architecture/gold-contract.md) states "Monetary values are
`Decimal` in the account's currency. No float enters the contract."
`silver-layer.md` types both `amount` and `balance` as `Decimal`.

**A wrong decimal is a refused import, not a rounding artefact.**
[ADR-006](../decisions/ADR-006-balance-chain-reconciliation.md) verifies each link by
testing whether the later balance equals the earlier balance plus the later amount, in
the bank's own row order.
[ADR-010](../decisions/ADR-010-quarantine-inconsistent-exports.md) turns a break into a
quarantine of the whole import run: "Nothing from that export reaches Silver until the
cause is resolved." Float drift of 1e-12 is therefore not cosmetic — it refuses a file
that was correct.

**Bronze must absorb source shapes it has never seen.**
[`bronze-layer.md`](../architecture/bronze-layer.md) types a parsed record as
`fields: Mapping[str, str]` — source field name to value exactly as decoded — rather than
a fixed column set, and stores the payload itself as `content: bytes` keyed by
`payload_id`, the SHA-256 of those bytes. Conforming happens in Silver, which emits one
source-neutral `Transaction` carrying `source_system`. A second bank, or a second ingest
method from the same bank, therefore adds a parser rather than a Silver or Gold schema
change. The store needs a map-shaped column and a binary column; it does not need an
exceptional migration story for this.

**The Gold model is a star with three facts at two grains.**
[ADR-007](../decisions/ADR-007-dimensional-gold-model.md) and
[ADR-008](../decisions/ADR-008-category-allocation-grain.md), both Accepted, give Gold
`GoldTransaction`, `GoldCategoryAllocation`, and `MonthlyBalanceSnapshot` over conformed
Account, Category, and Date dimensions. Dimensions are Type 1, keyed by durable
household-assigned identifiers, so no surrogate-key generation is needed. Evaluating the
balance chain needs an ordered window (`LAG` partitioned by account, ordered by
`(transaction_date, day_sequence)`), and the monthly snapshot needs one row per account
per month "including months with no transactions", so the store must be able to generate
a dense calendar.

**A rebuild must be deterministic.** `silver-layer.md`: "Rebuilding from the same Bronze
inputs, account configuration, and manual decisions yields identical output, including
identifiers."

**Publication belongs to issue #8, but it constrains storage.** `gold-contract.md`
invariant 15: "A consumer reads exactly one Gold publication at a time. Which
publication is selected, and identity across materializations, are defined by issue #8."
Whatever #8 decides, the store must let one materialization be built while readers read
another, and then swap.

**Only Gold has a storage-neutral seam.** `gold-contract.md` states "The persistence
technology is not part of this contract" and defines `GoldRepository` as the sole
consumer interface, so analytics and presentation never see the engine. That seam exists
only at Gold; Bronze and Silver have typed data contracts but no repository protocol, so
swapping their store means rewriting persistence code. The rebuild property above, not
this interface, is what makes the decision reversible.

## Measured scale, and why it decides nothing

Aggregate counts from `imports/` on 2026-09-19, excluding the synthetic `imports/mwe`
fixtures: 2 real exports, roughly 900 booked rows, spanning 2025-08-15 to 2026-09-14.
These are proof-of-concept samples rather than the archive, so they indicate a rate, not
a total. Danske serves at most 2.5 years of history. Four accounts at this rate stay
below roughly 10,000 rows for many years; the largest single export observed is 668 rows.

**Scale does not discriminate between any of the candidates and is not evaluated
further.** Every option answers a full scan of this data in milliseconds. Arguments that
turn on throughput, indexing strategy, or query planning are irrelevant here, and their
absence below is deliberate rather than an oversight.

## The archive and the store are different things, with opposite rules

The raw bank exports live in a OneDrive-synchronised folder outside this repository.
`imports/` in the working tree is proof-of-concept scratch, not the archive. The
application's own copy of the payload bytes is deliberately a *second* copy, so that a
`payload_id` mismatch between folder and store is detectable.

**The archive belongs in OneDrive.** It is the one irreplaceable asset — exports age out
of the bank's reach after about 2.5 years — and sync gives it off-machine durability and
version history with no maintenance. Files are written once, closed, and then synced, so
none of the failure modes below apply to them. The one caveat is
[Files On-Demand](https://support.microsoft.com/en-us/onedrive/save-disk-space-with-onedrive-files-on-demand-for-windows):
"When you open an online-only file, it downloads to your device and becomes a locally
available file" — so a first read of an archived export can block on the network, and an
offline machine may fail to open a file that appears to be present.

**The database file must not be in a synchronised folder.** SQLite's
[How To Corrupt An SQLite Database File](https://www.sqlite.org/howtocorrupt.html)
describes a sync agent generically, without naming one:

> Systems that run automatic backups in the background might try to make a backup copy
> of an SQLite database file while it is in the middle of a transaction. The backup copy
> then might contain some old and some new content, and thus be corrupt.

and

> unlinking or renaming an open database file results in behavior that is undefined and
> probably undesirable.

Those two clauses describe a local file copied and replaced by another process, which is
exactly what a sync agent does. WAL mode compounds it, because
[WAL](https://www.sqlite.org/wal.html) creates `-wal` and `-shm` sidecars in the same
directory, which the sync client will also try to upload. The failure mode is
intermittent by nature —
[SQLite Over a Network](https://www.sqlite.org/useovernet.html) warns that this class of
problem is "not frequent or repeatable" and that developers should "not rely on early
testing success".

Microsoft publishes no general rule about database files in OneDrive; its
[restrictions and limitations](https://support.microsoft.com/en-us/onedrive/restrictions-and-limitations-in-onedrive-and-sharepoint)
page does not mention them. The nearest official statement is about Access:
"Although you can save an Access database file to OneDrive or a SharePoint document
library, we recommend that you avoid opening an Access database from those locations…
The file might be downloaded locally for editing and then uploaded again after you save
your changes." That supports the rule by naming the same mechanism, not by naming SQLite;
it is cited here for the mechanism and nothing more.

This matters because Windows commonly redirects `Documents` into OneDrive by default, so
a store created at a default path can end up synchronised by accident. **Issue #10 must
state where the database file lives and that it is outside any synced folder.**

## Constraints on the import mechanism

The import mechanism is undecided and belongs to
[issue #11](https://github.com/ATherkel/budget/issues/11). This research assumes nothing
about it beyond two constraints it has to satisfy:

- **The original filename must survive.** `bronze-layer.md` reads `exported_on` from the
  Danske `-YYYYMMDD` filename suffix and retains `original_filename` as provenance. A
  flow that renames or strips the filename forces a manual `covers_through` declaration,
  and a wrong one "is not a visible error": too early "silently truncates the account's
  evidence", too late "silently manufactures confirmed zeros over months the export never
  covered".
- **The storage choice must not presume a particular import path.** Nothing recommended
  here requires the application process to have filesystem access to the archive folder.

## Evidence by requirement

### Exact decimal handling

**SQLite has no decimal type, and `NUMERIC` is the trap rather than the answer.**
[Datatypes in SQLite](https://www.sqlite.org/datatype3.html) defines five storage classes
— NULL, INTEGER, REAL, TEXT, BLOB — and specifies that "When text data is inserted into a
NUMERIC column, the storage class of the text is converted to INTEGER or REAL (in order
of preference)". The
[Python `sqlite3` type table](https://docs.python.org/3/library/sqlite3.html) maps REAL to
`float` and INTEGER to `int`; `decimal.Decimal` appears nowhere in it, and converters are
off by default.

The decisive point is that
[STRICT tables](https://www.sqlite.org/stricttables.html) forbid the trap outright: "The
datatype must be one of the following: INT / INTEGER / REAL / TEXT / BLOB / ANY. No other
datatype names are allowed." **Integer minor units is therefore not a workaround grafted
onto SQLite; it is the only exact-money representation its type system offers**, and a
`STRICT` table makes the database itself reject anything that is not an integer.

**DuckDB has real fixed-point decimals, but its Python return types are undocumented.**
[Numeric types](https://duckdb.org/docs/current/sql/data_types/numeric.html): "The data
type DECIMAL(WIDTH, SCALE)… represents an exact fixed-point decimal value", width 1–38,
with arithmetic that "throws an error" rather than silently degrading. Two hazards: a
bare `DECIMAL` binds to `DECIMAL(18, 3)` rather than being unconstrained as in
PostgreSQL, and division "uses approximate floating-point arithmetic… and accordingly
returns floating-point data types". More significantly, DuckDB's
[Python conversion page](https://duckdb.org/docs/current/clients/python/conversion.html)
documents Python→DuckDB only and publishes no DuckDB→Python scalar table, so "a DECIMAL
column returns `decimal.Decimal`" is not a documented guarantee. Measured on duckdb
1.5.5: `fetchone()` returns `Decimal('1234.56')` exactly, but `.df()` returns pandas
`float64` — and dashboard code reaches for `.df()` by default.

**PostgreSQL is the only candidate where exactness is documented in both directions.**
[Numeric types](https://www.postgresql.org/docs/current/datatype-numeric.html): `numeric`
is "especially recommended for storing monetary amounts and other quantities where
exactness is required".
[psycopg 3](https://www.psycopg.org/psycopg3/docs/advanced/adapt.html): "Normally
PostgreSQL numeric values are converted to Python Decimal instances, because both the
types allow fixed-precision arithmetic and are not subject to rounding." Returning floats
instead is an explicit opt-in the docs warn "may imply a loss of precision".

**Parquet formalises the same idea SQLite makes you implement by hand.**
[Logical Types](https://github.com/apache/parquet-format/blob/master/LogicalTypes.md):
"DECIMAL annotation represents arbitrary-precision signed decimal numbers of the form
unscaledValue * 10^(-scale). The primitive type stores an unscaled integer value." An
unscaled integer plus a scale is exactly the integer-øre design, standardised.

### Dimensional queries

All four support the SQL a star schema needs, including the window functions the balance
chain requires. This requirement discriminates nothing and is recorded only to show it
was checked. Measured on this machine: `LAG(...) OVER (...)`, `json_extract`, and
`json_each` all execute in the SQLite build bundled with CPython 3.12.3.

### Migrations and schema evolution

SQLite's [ALTER TABLE](https://www.sqlite.org/lang_altertable.html) is the most limited of
the three databases and documents a table-rebuild procedure for changes it cannot express
directly. In this project that limitation is largely defused by conform-at-Silver: a new
bank or ingest method adds a parser, not a Silver or Gold column.

The real discriminator here is tooling maturity.
[SQLAlchemy's dialect documentation](https://docs.sqlalchemy.org/en/20/dialects/index.html)
lists SQLite and PostgreSQL as included, first-party dialects. **DuckDB appears neither
as an included dialect nor on the maintained external-dialect list.** The community
[`duckdb_engine`](https://github.com/Mause/duckdb_engine) is a single-maintainer project
whose README states Alembic "support can be enabling by adding an Alembic implementation
class for the duckdb dialect" — that is, you write it yourself.

### Storage-format stability

[SQLite](https://www.sqlite.org/formatchng.html) makes the strongest commitment of the
four: "There are literally trillions of SQLite database files in circulation and the
SQLite developers are committing to supporting those files for decades into the future…
newer versions of SQLite can always read and write database files created by older
versions."

[DuckDB](https://duckdb.org/docs/current/internals/storage.html) guarantees backward
compatibility from v0.10 onward, but forward compatibility "is provided on a best effort
basis… may be (partially) broken on occasion", and the documented remedy when it breaks
is an `EXPORT DATABASE` / `IMPORT DATABASE` round trip. Note that the common belief that
"1.0 froze the format" is not what the docs say; what they say is that the default
written format is pinned to version 64 (v1.0.0) and newer formats are opt-in.

[PostgreSQL](https://www.postgresql.org/docs/current/upgrading.html) changes its internal
storage format across major releases: "The traditional method for moving data to a new
major version is to dump and restore the database… A faster method is pg_upgrade." In a
Docker context, pulling a new major image over an existing volume will refuse to start —
a recurring annual chore.

For Parquet, no explicit "newer readers can always read older files" promise was found;
the format's README frames stability as extensibility points only.

### Concurrency — the requirement that decided this

**SQLite documents the needed configuration exactly.**
[WAL](https://www.sqlite.org/wal.html): "WAL provides more concurrency as readers do not
block writers and a writer does not block readers… However, since there is only one WAL
file, there can only be one writer at a time", and "All processes using a database must
be on the same host computer". [When To Use](https://www.sqlite.org/whentouse.html):
"SQLite supports an unlimited number of simultaneous readers, but it will only allow one
writer at any instant in time… Writers queue up."

**DuckDB's documented modes exclude it.**
[Concurrency](https://duckdb.org/docs/current/connect/concurrency.html) offers exactly
two: "Read-write mode: one process can both read and write to the database" and
"Read-only mode: multiple processes can read from the database, but no processes can
write". There is no documented mode in which one process writes while another attaches
read-only. The documented escapes are the Quack protocol, "in beta stage as of DuckDB
v1.5.2", or DuckLake "with PostgreSQL as the catalog database" — which means operating
PostgreSQL *and* DuckDB.

**PostgreSQL handles it unremarkably**; no citation-worthy limitation exists at this scale.

**Parquet has no read isolation during a rewrite.** DuckDB's Parquet export options
"remove the existing directories", and no primary source offers isolation for a reader
globbing the tree mid-rebuild. It is safe only if a rebuild writes a new directory and
swaps.

### Private and household access

SQLite and DuckDB are serverless and have no authentication of their own; access control
is the application's responsibility. PostgreSQL has `scram-sha-256` and `pg_hba.conf`.

**This is not the advantage it appears to be.** Postgres authentication authenticates the
*application* to the *database*. The household requirement is that two people reach a
dashboard over the LAN, which is the FastAPI layer's responsibility under every
candidate, and is unaffected by the storage choice. Binding beyond localhost is a Uvicorn
`--host` setting in all four cases.

### Backup and restore

The store is derived and disposable, so this axis carries far less weight than it
normally would; what matters is that rebuild works, which `silver-layer.md` already
requires and which is testable. For completeness: SQLite has `VACUUM INTO` and a backup
API, DuckDB has `EXPORT DATABASE`, PostgreSQL has `pg_dump` (which "does not block other
users accessing the database") together with an explicit warning that filesystem-level
copies of a running cluster are unsafe, and Parquet files are ordinary files.

The archive, not the store, is what genuinely needs protection, and OneDrive already
provides it.

### Semi-structured columns for `SourceRecord.fields`

SQLite's JSON functions have been built in since 3.38.0 (2022-02-22) and are present in
the build CPython ships — measured here as SQLite 3.45.1 with `json_extract` and
`json_each` working, since CPython does not document which SQLite version or compile
flags it bundles. DuckDB has a native `MAP` type and an autoloading JSON extension.
PostgreSQL's answer is `jsonb`, with the caveat that it is lossy relative to the source
text — it discards whitespace, key order, and duplicate keys — which matters for a layer
whose contract is "exactly as decoded"; `json` preserves the text but cannot be indexed.
Parquet has a `MAP` nested type.

### Binary payload storage

All four store the bytes losslessly, and 3 MB troubles none of them. SQLite's BLOB is
"stored exactly as it was input", maps to Python `bytes` with no configuration, and is
capped at 1 GB by default.

SQLite is the only candidate whose project publishes measured guidance on this exact
question, and it favours the chosen design.
[35% Faster Than The Filesystem](https://www.sqlite.org/fasterthanfs.html): "SQLite reads
and writes small blobs (for example, thumbnail images) 35% faster than the same blobs can
be read from or written to individual files on disk", and
[Internal Versus External BLOBs](https://www.sqlite.org/intern-v-extern-blob.html) puts
the crossover where filesystem storage starts to win at roughly 50–100 KB. The exports
are tens of KB, inside the range where SQLite's own measurements favour in-database
storage.

DuckDB's [blob page](https://duckdb.org/docs/current/sql/data_types/blob.html) advises the
opposite — "typically it is not recommended to store very large objects within the
database system" — though "very large" and "tens of KB" are different regimes, so the two
projects are reconcilable rather than contradictory.

### Maintainer effort and moving parts

SQLite is in the Python standard library: zero dependencies. DuckDB and pyarrow are one
and two pip dependencies respectively.

PostgreSQL in Docker Desktop on this machine carries two documented problems.
[Docker's Windows install requirements](https://docs.docker.com/desktop/setup/install/windows-install/)
list "Windows 10 64-bit: Enterprise, Pro, or Education version 22H2 (build 19045)" for
the WSL 2 backend — Home is absent — while a note on the same page states "Windows Home
or Education editions only allow you to run Linux containers", which presupposes Home
works. That is an unresolved contradiction within Docker's own documentation, read
2026-09-19; the machine's build number 19045 matches, and only the edition is in
question. Separately,
[Windows 10 reached end of support on 2025-10-14](https://learn.microsoft.com/en-us/lifecycle/products/windows-10-home-and-pro),
roughly eleven months before this research.

The honest moving-parts count: Windows 10 Home (out of support) → WSL 2 → Docker Desktop
→ a Postgres container → a named volume → `pg_hba.conf` → `psycopg` → an annual major
version upgrade. Against: the standard library.

## Measured: what SQLite does with money on this machine

Not a citation. This is a measurement taken on 2026-09-19 on the maintainer's machine,
Python 3.12.3 with bundled SQLite 3.45.1, and is reported because it makes the cited
type-affinity behaviour concrete.

Three `Decimal` values were written through a `NUMERIC` column, a `TEXT` column, and an
`INTEGER` column holding øre:

| Written | via `NUMERIC` | via `TEXT` | via `INTEGER` øre |
| --- | --- | --- | --- |
| `-45.00` | `-45` (`int`) | `'-45.00'` | `-4500` → `-45.00` |
| `12847.53` | `12847.53` (`float`) | `'12847.53'` | `1284753` → `12847.53` |
| `0.10` | `0.1` (`float`) | `'0.10'` | `10` → `0.10` |

`SUM` over the `NUMERIC` column returned `12802.630000000001`; over the `INTEGER` column
it returned `1280263`, which is `12802.63` exactly. The true total is `12802.63`.

That trailing `0000000001` is an ADR-010 quarantine of a correct export: the chain check
compares a stated balance against a computed one, they differ by about 1e-12, and the
import is refused. Separately, `sqlite3` refuses to bind a `Decimal` at all —
`ProgrammingError: Error binding parameter 1: type 'decimal.Decimal' is not supported` —
which is a useful property, because it fails loudly at the boundary instead of silently
coercing.

## Recommendation

**SQLite, amounts as `INTEGER` minor units, `STRICT` tables, WAL mode, database file
outside any synchronised folder.**

What it wins on:

- Concurrency matching the stated need, documented rather than inferred.
- Zero dependencies, which is the direct answer to the maintainer's stated dealbreaker.
- The strongest file-format stability commitment of the four.
- Published, measured guidance endorsing the in-database payload copy at this size.
- First-party SQLAlchemy and Alembic support if a schema-management layer is wanted.
- `STRICT` plus `INTEGER` moves the money invariant into the database's own type checking.

What it costs, stated plainly:

- **A conversion adapter between `Decimal` and integer minor units is code the household
  owns and must test.** The exposure is narrower than it first appears — ADR-009 already
  quantizes amounts to the minor unit before storage, so the adapter converts an
  already-quantized value, and ADR-005 requires it be built test-first — but it is real,
  and PostgreSQL would not have it.
- SQL-level sums are in øre, so any query written by hand returns integers that mean
  hundredths. That is exact, but it is a foot-gun for a future reader of the code.
- No native authentication. This is not a real cost, because household access is the
  FastAPI layer's job under every candidate.
- `ALTER TABLE` is the most limited of the three databases, mitigated by conform-at-Silver
  and by the fact that a rebuild is always available.

Explicitly rejected, with reasons:

| Candidate | Why not |
| --- | --- |
| Plain SQLite with `NUMERIC` | Silently stores money as IEEE-754 float; `STRICT` tables forbid the type outright. Cut by the maintainer before the research began. |
| DuckDB | Its documented concurrency modes have no configuration in which one process writes while another reads. The escapes are a beta protocol or running PostgreSQL alongside it. Absent from SQLAlchemy's dialect documentation. |
| PostgreSQL in Docker | Wins on decimals, migrations, and isolation from the OneDrive hazard. Loses on moving parts, on a platform out of support since 2025-10-14, with an edition Docker's own requirements do not list. |
| Parquet + DuckDB | No documented read isolation while a rebuild rewrites the tree; several round-trip properties unverifiable from primary sources; inherits DuckDB's concurrency model. |

## What the maintainer decided in this session, and what each answer changed

Recorded so the reasoning survives the decision.

| What was asked | Answer | What it changed |
| --- | --- | --- |
| Scale and history horizon | Corrected the researcher: `imports/mwe` is synthetic; real data is 2 exports, ~900 rows | Estimate corrected, conclusion unchanged — scale discriminates nothing |
| Future sources | Nordea certain; a Danske **API** ingest intended, possibly a different record shape | Killed "one bank forever"; raised an ADR-009 problem (see below) |
| Host machine and process tolerance | Docker Desktop acceptable | Kept PostgreSQL in the shortlist through to the final trade |
| What backup means | "I'd re-import" — the exports are the record, the database is remade | Killed single-file portability as a *requirement*, removing the strongest early argument for SQLite/DuckDB. It had to be re-won on other grounds, and was |
| Dealbreaker | "It became a maintenance project" | Made moving parts the tiebreaker rather than a soft preference; put PostgreSQL on notice |
| Shortlist | Cut plain SQLite, keep the øre variant | Plain SQLite dropped before research; its type-affinity behaviour retained only as justification |
| Where the exports live | Both: OneDrive folder *and* a copy inside the store, deliberately, for cross-checking | Retracted a concern about `imports/` being unprotected; added the binary-storage axis and the sync-corruption rule |
| Ingest robustness | "If the design docs… aren't robust for a change in ingest method, I should start over. Extract, Clean, **Conform**, Deliver" | **Reversed the researcher's own framing.** Migrations had been called a dominant requirement; conform-at-Silver defuses them, which removed PostgreSQL's strongest advantage |
| Import mechanism | Deferred to issue #11 | Nothing died; two constraints recorded against #11 instead |
| Process topology | "Don't want to be forced either way" | **Decided the outcome.** Eliminated DuckDB, on DuckDB's own documentation rather than on preference |
| The final trade | SQLite, own the adapter | PostgreSQL and Parquet+DuckDB eliminated |

Two corrections the research made to its own earlier reasoning are worth keeping: scale
was initially measured including synthetic fixtures, and migrations were initially
weighted as a dominant requirement before the conform-at-Silver design was accounted for.
Both are recorded above rather than quietly fixed.

## Raised, not resolved: ADR-009 does not survive the API ingest as written

Not a storage question, and not this ticket's to settle, but it surfaced here and should
not be lost. ADR-009 derives identity from content and occurrence precisely because
"Danske CSV exports carry no transaction, account, or currency identifier". An API
response very likely *does* carry one. The same booked transaction arriving once as a CSV
row and once as an API record would not produce the same hash, so it would present as two
transactions — and the merge rules in `silver-layer.md` would see an export that fails to
show an already-admitted transaction. Conform-at-Silver is the right shape for the
answer, but ADR-009 would need to say what identity means when one account has two
ingest methods. That belongs with the import-identity work, not here.

## Decisions deliberately left open

These are what issue #10 has to record. None is settled by this research.

- **Whether to accept the recommendation at all.** The evidence supports SQLite with
  integer minor units; the choice is the maintainer's.
- **Where the database file lives.** It must be outside any synchronised folder; the
  actual path, and whether it sits beside the repository or in a data directory, is
  unstated.
- **The minor-unit convention.** Whether the scale is per-currency and stored, or fixed at
  two digits for DKK with a documented assumption. `gold-contract.md` allows ISO 4217
  currencies and forbids aggregating across them; the first release is DKK only.
- **Whether `STRICT` tables and WAL mode are adopted**, which this research recommends but
  does not decide.
- **Whether SQLAlchemy and Alembic are adopted, or the standard library `sqlite3` module
  is used directly.** Both are first-party-supported for SQLite; this is a maintenance
  preference, not an evidence question.
- **Whether DuckDB is later attached as a read-only query engine over the SQLite file for
  analytics.** It is ruled out here as the *system of record* only. Using it purely as a
  reader avoids the concurrency finding entirely, at the cost of one more dependency.
- **How household access to the dashboard is authenticated**, which is the presentation
  layer's question and unaffected by the storage choice.
- **How publication swaps materializations** (issue #8). SQLite transactions are atomic,
  so a swap within one database is expressible, but whether publications are separate
  files or rows in one file is #8's to decide.
- **Whether the archive folder needs protection beyond OneDrive's own sync and version
  history**, given that exports age out of the bank's reach after roughly 2.5 years.

This research resolves the evidence question in issue #9: which options meet the accepted
contracts, and which are eliminated by their own documentation. It does not resolve the
stack decision, which is issue #10's to record.

## Gaps in the evidence

Stated so that no claim above is read as better supported than it is.

- **DuckDB publishes no DuckDB→Python scalar type mapping.** That `DECIMAL` returns
  `decimal.Decimal` was verified by measurement on duckdb 1.5.5, not from documentation.
  `BLOB → bytes` was neither documented nor tested.
- **Arrow's documented Arrow→pandas conversion table omits DECIMAL entirely.** The common
  claim that pandas has no decimal dtype is not stated on that page. Parquet decimal
  round-trip was verified by measurement only.
- **Parquet map and `bytes` round-trips were not verified**, and no per-value size limit
  for `BYTE_ARRAY` was found in the specification.
- **No explicit Parquet reader-compatibility promise was found** equivalent to SQLite's.
- **CPython does not document which SQLite version or compile flags it bundles.** The
  JSON1 availability claim rests on SQLite's opt-out policy from 3.38.0 plus a local
  measurement.
- **Introduction versions are unverified** for SQLite CTEs, PostgreSQL window functions,
  and PostgreSQL `jsonb`; the current documentation pages do not state them. Irrelevant
  at current versions.
- **`hstore` was not examined**, so nothing here should be read as an assessment of it.
- **Microsoft publishes no official guidance** that database files or files held open by
  an application should not live in OneDrive. The Access article is cited above for the
  mechanism it describes, not as a general rule.
- **DuckDB publishes no corruption-modes document and no statement about cloud-sync
  folders.** Its entire documented position is a two-sentence caution about shared
  directories. The absence is itself the finding: for DuckDB the sync risk is
  undocumented, not documented as safe.
- **DuckDB makes no claim about being or not being a system of record.** Its positioning
  page describes it as designed for OLAP workloads and contrasts it with PostgreSQL and
  MySQL for row-by-row transactional processing, but says nothing about durability
  guarantees. No inference was drawn from the silence.
