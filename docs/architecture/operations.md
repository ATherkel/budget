# Operations

Status: proposed ([ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md)).
Resolves [issue #10](https://github.com/ATherkel/budget/issues/10) once
accepted.

## Purpose

This document says how the household runs the pipeline: where every file
lives, how production, development and test stay apart, what the household
edits and in which format, which commands exist, what happens when something
fails, and how everything is backed up and restored. Every example is
synthetic.

It relies on these decisions:

- [ADR-013](../decisions/ADR-013-sqlite-store-integer-minor-units.md): SQLite
  through `sqlite3`, `STRICT` tables, WAL mode, integer minor units, numbered
  SQL migrations, and backups through the backup API.
- [ADR-014](../decisions/ADR-014-gold-publications-and-history.md) (proposed
  in pull request #57): publications, recipes, immediate promotion with `undo`,
  retention, past views, and the append-only decision log.
- [ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md):
  profiles, one store per ETL stage, one file per publication, development
  from backups, and household inputs as text.

Three principles apply throughout:

- **Production is written only by pipeline commands.** No test, ad hoc SQL
  session, or hand edit writes a production store.
- **Everything a person says is text; everything a bank says is a file.** The
  stores can be rebuilt from the export archive and the inputs folder. Backups
  make that fast, not possible.
- **Financial values reach the operator's terminal, never a log.**

## Stores

Each ETL stage persists its output in its own SQLite store. Kimball's ETL
subsystems name the steps *extract*, *clean*, *conform* and *deliver*, and
save the data after each so a failure restarts from the last completed step.
Here the saved steps are the stores.

| Store | Step | Holds | Rebuildable from | In a backup set |
| --- | --- | --- | --- | --- |
| `bronze.db` | Extract | Raw payloads, import runs, source records, format failures | The export archive and the import log | Yes |
| `silver.db` | Clean and conform | Canonical transactions, unbooked records, validation errors, import review items, evidence | Bronze and the inputs | Yes, so development can start from it |
| `gold/catalog.db` | Deliver: control | Recipes, configuration snapshots, the current pointer and its history, labels | No: recipes are history | Yes |
| `gold/publication-<id>.db` | Deliver | One publication's Gold tables and lineage | Its recipe, replayed with its code (ADR-014) | The retained ones |

Kimball's *conform* step also builds the conformed dimensions. Here those
(account, category, date) are built in Gold from the household inputs,
because Silver's conforming is per source and Gold's dimensions are the
household's.

Rules for every store:

- **Created only by `migrate`.** Each store has its own numbered migrations,
  in `migrations/bronze/`, `migrations/silver/`, `migrations/catalog/` and
  `migrations/publication/`, and its own `PRAGMA user_version`. Opening a store
  never creates tables and fails when the file does not exist (ADR-013).
- **It knows its profile and stage.** `migrate` writes `profile` and `stage`
  into a one-row `store_identity` table when it creates the store. Opening a
  store under another profile or as another stage is refused.
- **A publication file keeps its schema version.** A Gold migration changes
  the schema that new publications are written with. It does not convert the
  retained files. The running code refuses to open a publication whose schema
  version differs from its own and names the code version that can.
- **A write to one store is one transaction.** Silver and Gold commit
  separately. Readers only reach Gold through the pointer, so a crash between
  the two leaves the previous publication current.

### Publishing a Gold build

1. Write `publication-<id>.db` completely, compute its result fingerprint, and
   close the file.
2. In `catalog.db`, in one transaction, store the recipe, register the
   publication, and move the pointer (ADR-014: promotion is immediate). **This
   transaction is the commit point.**
3. Delete the result files that are no longer retained: not current, not
   previous, not labeled.

A crash before step 2 leaves a file the catalog does not know. The next
command deletes it. Step 3 can fail on Windows while the dashboard has the file
open; a later command retries it.

The dashboard reads the pointer from `catalog.db` for each page, opens the
named file read-only, and pins that `publication_id` across the page's
requests (ADR-014). Past views (`view --as-was`, `view --known-at`) are
publication files too and can never become current. The Silver that an
as-known-at view builds from a subset of import runs goes to the profile's
`scratch/` folder and is deleted afterwards.

## Profiles

A profile is a configuration of the same code. It names every path the
application touches.

| | Production | Development | Test |
| --- | --- | --- | --- |
| Data | Real exports | Production's latest backup set | Committed synthetic fixtures |
| Stores | Its own, on the home machine | `upstream/` (read-only) plus its own diverged stores | A temporary directory per run |
| Inputs | The household's inputs folder | A working copy of it | Fixture files |
| Written by | Pipeline commands only | Pipeline commands; experiments allowed | The test run |
| Lifetime | Permanent | Until the next `dev refresh` | Created and destroyed by each run |
| Migrations | Backup first, then migrate | Rehearsed here before production | From empty, every run |
| Dashboard | Home network, with a passphrase | This PC only | Not served; tested in-process |

### Selecting a profile

- `budget --profile <file> …`, or the `BUDGET_PROFILE` environment variable
  naming the file. With neither, every command refuses to run. There is no
  default, because a default would be production, and a test run inherits the
  operator's shell.
- Profile files live outside the repository, for example in
  `%APPDATA%\budget\`. They hold paths only, no secrets.
- **Test profiles are never files.** The test suite builds each profile in a
  temporary directory and refuses a store path outside it. No test reads
  `imports/`, a profile file, or `BUDGET_PROFILE`
  ([`tdd.md`](../agents/tdd.md)).

```toml
# %APPDATA%\budget\production.toml
format = 1
profile = "production"

[paths]
stores  = 'C:\Users\household\AppData\Local\budget\production'
inbox   = 'C:\Users\household\OneDrive\Budget\inbox'
exports = 'C:\Users\household\OneDrive\Budget\exports'
inputs  = 'C:\Users\household\OneDrive\Budget\inputs'
backups = 'C:\Users\household\OneDrive\Budget\backups'

[dashboard]
bind = "192.168.1.20"
port = 8750
```

A development profile has `profile = "development"`, its own `stores` and
`inputs`, and `upstream_backups` naming production's `backups` folder, which
it only reads.

### Where production lives

```text
%LOCALAPPDATA%\budget\production\      live stores: never cloud-synchronised (ADR-013)
    bronze.db
    silver.db
    gold\catalog.db
    gold\publication-000042.db
    scratch\
    logs\
OneDrive\Budget\                       closed files only: safe to synchronise
    inbox\<account_id>\                exports waiting to be imported
    exports\<account_id>\              the export archive
    inputs\                            what the household says
        accounts.toml
        taxonomy.toml
        rules.toml
        decisions.jsonl
        imports.jsonl
    backups\<UTC timestamp>\           backup sets
```

### Development diverges from a stage

`dev refresh` restores production's newest backup set into development's
`upstream/` folder, and marks it read-only. `rebuild --from <stage>` rebuilds
that stage and every later one into development's own stores. The stages
before it are opened from `upstream/`, read-only, and never recomputed.

| What changed | Command | Reads from `upstream/` | Writes in development |
| --- | --- | --- | --- |
| Source parsing (Bronze code) | `rebuild --from bronze` | Raw payloads and import runs | `bronze.db` (source records re-derived), `silver.db`, `gold/` |
| Silver mapping, identity, or a Silver decision | `rebuild --from silver` | `bronze.db` | `silver.db`, `gold/` |
| Accounts, taxonomy, rules, a classification decision, or Gold code | `rebuild --from gold` | `bronze.db`, `silver.db` | `gold/` |

Development's inputs are a working copy. `dev refresh --inputs` replaces them
with production's; plain `dev refresh` leaves them alone. A development
publication built from uncommitted code is marked not reproducible (ADR-014).
Production builds refuse uncommitted code, so production runs from its own
clean checkout, separate from the one used for development.

## Household Inputs

Everything the household authors lives in the inputs folder as text. Every
file:

- is UTF-8;
- carries `format = 1` (TOML) or `"format": 1` on each line (JSON Lines), and
  an unknown format version is refused;
- rejects unknown keys, so a misspelt key is an error, not an ignored line;
- uses durable, lowercase, hyphenated identifiers such as `joint-current`.

**Amounts are quoted decimal strings**, such as `"-1000.00"`. TOML reads an
unquoted `1000.00` as a binary floating-point number, which the platform
never accepts for money; an unquoted amount is a configuration error.

The files' history is the configuration snapshots in recipes (ADR-014) and
OneDrive's version history. They are not kept in a git repository: a `.git`
folder inside a synchronised folder risks exactly the inconsistent copies
ADR-013 keeps the live stores away from.

### `accounts.toml`

The account registry: only accounts inside the reporting boundary.

```toml
format = 1

[account.joint-current]
display_name = "Joint current"
account_type = "current"         # current | savings
ownership_scope = "household"    # household | person
currency = "DKK"
source_format = "danske-csv-v1"  # what its inbox folder receives

[account.joint-savings]
display_name = "Joint savings"
account_type = "savings"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
# closed_on = 2027-06-30         # set when the account closes
```

### `taxonomy.toml`

```toml
format = 1

[group.food]
name = "Food"
direction = "expense"            # income | expense; shared by its categories

[category.groceries]
name = "Groceries"
group = "food"

[category.eating-out]
name = "Eating out"
group = "food"
```

A rename or regroup is also recorded in
[`category-changes.md`](../domains/category-changes.md).

### `rules.toml`

One `[[rule]]` block per classification rule. Every `when` condition must hold.
The `then` table has exactly one outcome.

```toml
format = 1

[[rule]]
id = "r-netto"
when.description_contains = "NETTO"
then.category = "groceries"

[[rule]]
id = "r-furniture"
priority = 10
when.description_contains = "IKEA"
when.amount_max = "-1000.00"
then.category = "furniture"

[[rule]]
id = "r-savings-transfer"
when.description_contains = ["TO SAVINGS", "FROM CURRENT"]   # any of these
then.transfer_claim = true

[[rule]]
id = "r-bank-groceries"
priority = -10
when.bank_category = "Groceries"
then.category = "groceries"

[[rule]]
id = "r-interest-correction"
when.account = "joint-savings"
when.description_starts_with = "RENTEKORR"
then.adjustment = "Bank's interest correction"
```

`when` keys: `account`, `description_contains`, `description_starts_with`,
`description_regex` (all case-insensitive; a list means any of them),
`amount_sign` (`"negative"` or `"positive"`), `amount_min`, `amount_max`,
`date_from`, `date_to` (inclusive), `bank_category`, `bank_subcategory`.
`priority` defaults to 0. The transfer matching policy (3 days) is a constant
of the code, not a file, and enters recipes through the code version.

### `decisions.jsonl`: the decision log

The append-only log of manual decisions (ADR-014), one JSON object per line.
Only `budget decide` writes it. It is JSON Lines rather than TOML because the
application writes it: Python's standard library writes JSON, but only reads
TOML.

```json
{"format": 1, "entry": 1, "decision_id": "d-0001", "recorded_at": "2026-04-10T17:02:11Z", "kind": "classify", "targets": ["7c1e0b9a4d2f…"], "category": "gifts", "reason": "Wedding present", "supersedes": null}
{"format": 1, "entry": 2, "decision_id": "d-0002", "recorded_at": "2026-04-11T08:40:37Z", "kind": "pair", "targets": ["3f9a2c1e77b0…", "a04d6e12c9f3…"], "reason": "Settles an ambiguous transfer", "supersedes": null}
{"format": 1, "entry": 3, "decision_id": "d-0003", "recorded_at": "2026-04-12T19:15:02Z", "kind": "retract", "targets": [], "reason": "Was not a gift", "supersedes": "d-0001"}
```

Kinds: `classify`, `pair`, `one-sided-transfer` (ADR-011, ADR-012);
`void-import-run`, `same-transaction`, `withdrawn`, `accept-discrepancy`
(Silver, issue #5); and `retract`, which withdraws an earlier decision. It is
named `retract` so it is not confused with *withdrawn*, which records that the
bank removed a transaction. A new decision on a target that already has one
must name the old one in `supersedes`, or the boundary rejects it. Nothing is
edited in place.

Every recipe records the log position it read and a SHA-256 of the log up to
that position. `check` fails when that prefix no longer hashes the same, so a
hand edit to earlier entries is caught.

### `imports.jsonl`: the import log

One line per Bronze import run, mirroring Bronze's `ImportRun` plus the
archive path. It is what makes Bronze rebuildable from the archive, because
the declarations (account, `covers_through`, `started_at`) exist nowhere
outside Bronze.
Every command that writes Bronze brings it up to date before it finishes, and
`verify` checks that the two agree.

```json
{"format": 1, "import_run_id": "run-0001", "account_id": "joint-current", "source_format": "danske-csv-v1", "archive_path": "joint-current/export-20260402.csv", "payload_sha256": "c0ffee…", "exported_on": "2026-04-02", "exported_on_source": "filename", "covers_through": "2026-04-02", "covers_through_source": "exported_on", "started_at": "2026-04-02T18:03:44Z", "outcome": "stored", "repeat_of": null}
```

## The Validation Boundary for Decisions

Every manual decision passes one application boundary before it is recorded.
The CLI calls it now; a browser editor calls the same one later.

```python
class DecisionLog(Protocol):
    def propose(self, proposal: DecisionProposal) -> Recorded | Rejected: ...
    def entries(self) -> Sequence[DecisionEntry]: ...
```

`propose` checks the proposal against the configuration and the current
publication: the targets exist, the category exists, the kind applies (for
example, a `pair`'s amounts cancel), and no other effective decision targets
the transaction unless this one supersedes it. It then sets `entry`,
`decision_id` and `recorded_at`, appends the line and flushes it to disk, and
returns the entry. A rejection names every reason and records nothing.

The boundary sits in the application layer, not in presentation. The
dashboard stays read-only: it has no route that reaches the boundary.

## Commands

`budget [--profile <file>] <command>`. The CLI uses the standard library's
`argparse`.

| Command | Does | Writes | Publishes |
| --- | --- | --- | --- |
| `migrate [--stage <stage>]` | Creates or upgrades stores. In production, takes a backup set first. | Store schemas | No |
| `check` | Validates every input file and the decision-log prefix. Never builds. | Nothing | No |
| `import` | Imports every file in the inbox, then rebuilds and publishes. | Bronze, the import log, Silver, Gold | Yes, if the build succeeds |
| `rebuild [--from bronze\|silver\|gold]` | Rebuilds from a stage; `gold` by default. | Stages from `--from` on | Yes, if the recipe changed |
| `review [--kind <kind>] [--account <id>]` | Lists open review items, Silver's and Gold's, with what a person needs to settle each one. | Nothing | No |
| `decide <kind> <targets…> [options] --reason <text>` | Proposes a manual decision to the boundary, then rebuilds from the stage the decision affects. | The decision log, then stores | Yes |
| `status` | Shows balance and classification completeness (below). | Nothing | No |
| `undo` | Moves the pointer back (ADR-014). | Catalog | Pointer only |
| `view --as-was <date> \| --known-at <date> --label <text>` | Builds or finds a past view (ADR-014). | Catalog, a view file | Never current |
| `label <publication_id> <text>` / `unlabel …` | Keeps a result beyond the retention rule, or stops keeping it. | Catalog | No |
| `backup` | Writes a backup set. Also runs automatically; see below. | The backups folder | No |
| `restore <backup set>` | Restores into an empty profile, then runs `verify`. | Every store | No |
| `restore --from-archive` | Last resort: rebuilds Bronze from the archive and the import log, then Silver and Gold. | Every store | Yes |
| `verify` | Checks integrity and proves the current publication reproduces. | `scratch/` only | No |
| `dev refresh [--inputs]` | Development only: restores production's newest backup set into `upstream/`. | Development only | No |
| `serve` | Starts the read-only dashboard. | Nothing | No |
| `set-passphrase` | Sets the dashboard passphrase. | The passphrase file | No |

Review output shows each transaction with a short handle: the first 8
characters of its `transaction_id`. `decide` accepts a handle; a handle that
matches more than one transaction is refused.

`decide` rebuilds from Silver for `void-import-run`, `same-transaction`,
`withdrawn` and `accept-discrepancy`, and from Gold for the rest.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Done. Open review items and quarantined imports are results, not failures. |
| 1 | Usage error. |
| 2 | Refused input: a configuration error, a rejected decision, or an import run Bronze refused. Nothing was published. |
| 3 | Refused environment: no profile, a store from another profile, a missing or newer migration, SQLite below the version floor, uncommitted code in production, or a store locked past its busy timeout. |

### Error reporting

A configuration error names the file, the entry, and the problem, and `check`
lists every one before stopping:

```text
rules.toml: rule "r-mobilepay-netto": then.category "food-out" is not in taxonomy.toml
rules.toml: rule "r-furniture": when.amount_max must be a quoted decimal, got a number
decisions.jsonl: entry 7 (d-0007): targets a transaction already decided by d-0002
3 configuration errors. Nothing was built.
```

## Completeness Outputs

`status` shows, and `import`, `rebuild` and `decide` end with, the two
completeness checks the household needs before trusting a report:

- **Balance completeness, per account:** the latest export date, *evidence
  through*, quarantined import runs, and the coverage of each of the last
  months, including which periods are provisional and why.
- **Classification completeness, per account and month:** unclassified money
  in, money out and count, and open review items by kind, Silver's and Gold's
  separately.

Both go to the terminal only. Neither changes an exit code.

## Walkthroughs

All accounts, dates and amounts are synthetic, taken from
[`classification.md`](classification.md).

### W1: the monthly import

The household downloads two exports and saves them to
`inbox\joint-current\` and `inbox\joint-savings\`. The folder is the account
declaration (ADR-009).

```text
> budget import
joint-current   export-20260502.csv
  exported on   2026-05-02 (from filename)
  covers through 2026-05-02 (falls back to exported on)
  transactions  2026-04-01 … 2026-05-01, 58 source records
joint-savings   export-20260502.csv
  exported on   2026-05-02 (from filename)
  covers through? The payload's last transaction is 2026-01-31, in an earlier
                 month than 2026-05-01, so it must be declared.
  Enter the last date you asked the bank for: 2026-04-30
Import both? [y/N] y
Bronze   2 import runs stored
Silver   2 admitted, 0 quarantined
Gold     publication 43 is current (was 42)
Changes  April: income +12,000.00, expenses +3,450.00, unclassified out +1,000.00
Review   1 unmatched-transfer, 0 other
Backup   2026-05-02T18-05-11Z written
```

Bronze requires the `covers_through` declaration for the savings export
because the fallback would claim evidence into a later month than its last
transaction ([`bronze-layer.md`](bronze-layer.md)). Each file then moves to
`exports\<account_id>\` under its original name, which carries the export
date. When that name is already taken by different bytes, it goes to
`exports\<account_id>\<first 12 characters of the payload hash>\` instead.

### W2: settling a review item

```text
> budget review
unmatched-transfer  no-candidate
  3f9a2c1e  joint-current  2026-02-16  −1,000.00  TO SAVINGS
  settle with: classify, pair, one-sided-transfer, or a rule change
> budget decide classify 3f9a2c1e external-saving --reason "To Bo's savings, not imported"
Recorded d-0005. Gold publication 44 is current (was 43).
Changes  February: external-saving +1,000.00; unclassified out −1,000.00
```

### W3: changing a rule

Edit `rules.toml`, run `budget check`, then `budget rebuild`. The printed diff
shows what moved. If the diff is wrong, `budget undo` restores the previous
publication at once, and the rules file must still be fixed, or the next build
brings the change back (ADR-014).

### W4: trying a change in development first

```text
> $env:BUDGET_PROFILE = "$env:APPDATA\budget\development.toml"
> budget dev refresh --inputs
Restored backup set 2026-05-02T18-05-11Z into upstream (read-only)
> # edit the development copy of rules.toml
> budget rebuild --from gold
Gold     development publication 1 (from upstream silver.db)
Changes  February: groceries +85.00, unclassified out −85.00; 1 rule-conflict closed
```

When the diff is right, copy the rule into production's `rules.toml` and
rebuild there.

### W5: a migration

1. In development: `dev refresh`, `migrate`, `rebuild --from <the first
   stage the migration touches>`, and `verify`.
2. In production: `migrate`, which writes a backup set first, and then
   `verify`.

### W6: the machine dies

On the new machine: install the pinned code version, write the production
profile, run `budget restore <newest backup set>`, which runs `verify`, then
`budget serve`. At most the imports since the last backup set are missing,
and every import writes one. The inputs folder and the export archive are
already in OneDrive.

### W7: every backup set is lost

`budget restore --from-archive` rebuilds Bronze from the export archive and
`imports.jsonl`, then Silver and Gold from the inputs. Reports come back
exactly. Recipes and past views are lost, because they live only in
`catalog.db` and its backups.

## Failure and Retry

| Failure | Effect | Retry |
| --- | --- | --- |
| Configuration error | Nothing is built; exit 2 | Fix the file and rerun |
| Refused import run (account conflict, `covers_through` out of bounds) | Recorded as refused; the file stays in the inbox; exit 2 | Move the file or correct the declaration, then rerun |
| Format failure | Stored with its `FormatFailure`; Silver quarantines it; the file is archived | Settled by a parser fix and `rebuild --from bronze` |
| Crash during an import | Each file is idempotent: a file whose account, original filename and payload hash already have a `stored` or `repeat` run is finished (archived and removed from the inbox) without a new run | Rerun `import` |
| Crash during a build | The previous publication stays current; an unregistered publication file is deleted by the next command | Rerun the command |
| Store locked | Exit 3 after the busy timeout | Rerun when the other command ends |
| A retained file cannot be deleted | Nothing; the dashboard has it open | A later command deletes it |
| OneDrive offline | Backup sets wait in the local OneDrive folder | Nothing to do |

A genuine repeat export has a new export date in its filename, so it is
presented to Bronze as a new `repeat` run, as the Bronze rules require.

## Backup and Restore

- **A backup set** is a folder under `backups\<UTC timestamp>\` holding a
  snapshot of every store taken through SQLite's backup API, a copy of the
  inputs folder, and a `manifest.json` with the profile, the code version,
  each store's schema version and SHA-256, and the lengths of both logs. The
  export archive is not copied, because Bronze holds each payload's bytes.
- **When:** after every command that writes Bronze or publishes, and before
  every `migrate`. Only production writes backup sets.
- **Kept:** the 30 newest sets and the newest set of each calendar month.
- **Where:** OneDrive, which is safe for them: a backup set is closed files,
  unlike a live database with its WAL files (ADR-013).
- **`restore`** writes only into a profile with no stores, checks every
  SHA-256 against the manifest, runs `PRAGMA integrity_check`, migrates stores
  older than the code, and runs `verify`.
- **`verify`** runs `PRAGMA integrity_check` on every store, rebuilds Silver
  and Gold from Bronze into `scratch/`, and compares the result fingerprint
  with the current publication's (ADR-014). It also checks that the import log
  agrees with Bronze and that the decision-log prefix hashes match.

## Dashboard Access

- `serve` binds to the address and port in the profile: the machine's home
  network address in production, and `127.0.0.1` in development. A Windows
  firewall rule allows the port on private networks only. Nothing is reachable
  from the internet.
- One household passphrase guards every page. It is stored as a `scrypt` hash
  in a file under `%APPDATA%\budget\`, never in OneDrive or the repository. A
  successful login sets an `HttpOnly`, `SameSite=Strict` session cookie.
  Repeated failed logins are slowed down.
- **Plain HTTP on the home network is an accepted risk.** Someone on the same
  Wi-Fi who captures traffic could read the passphrase and pages. HTTPS with a
  locally trusted certificate is the upgrade path if that changes.
- The dashboard opens `catalog.db` and publication files read-only and is
  given no other path. It has no route that writes, apart from login and
  logout.
- It runs while `budget serve` runs. Starting it with Windows is an optional
  Task Scheduler entry.

## Logging

Routine logs are JSON Lines under the profile's `logs\` folder, rotated by
size.

- **Allowed:** the command, profile, event, counts, durations, schema and code
  versions, error codes, and the identifiers `import_run_id`,
  `publication_id`, `decision_id`, and review item kinds.
- **Never:** amounts, balances, descriptions, bank category labels, original
  filenames, or `transaction_id`s, which are hashes of transaction content.

A test runs every walkthrough on synthetic data and asserts that no fixture
amount, description or filename appears in the log.

## Proved Outside Production First

A procedure runs in production only after it has passed in the test profile
and run at least once in development against a restored production backup.

| Procedure | Test profile, every CI run | Development |
| --- | --- | --- |
| `migrate` | Every migration from empty, and from the previous release's fixture stores | Rehearsed on a fresh `dev refresh` before production |
| Import and its retry | Idempotent rerun, and a crash injected after each step | Real exports' shapes, through `upstream` |
| Publishing | Crash before and after the commit point; `undo`; orphan and retry deletion | Every `rebuild` publishes |
| Backup and restore | Backup, restore into an empty profile, `verify` | Every `dev refresh` is a restore |
| `restore --from-archive` | Rebuilds the fixtures' reports exactly | Once before it is first trusted, then yearly |
| Log redaction | Asserted on every walkthrough | — |
| Profile guards | Every refusal: no profile, wrong profile, test path outside the temporary directory | — |

## Tooling

- `uv` with a uv-managed Python 3.12 or newer, whose SQLite meets ADR-013's
  floor, on the household machine and in CI.
- The CLI uses only the standard library: `argparse`, `tomllib`, `json`,
  `sqlite3`, `hashlib`, `logging`. The dashboard adds its presentation stack
  (FastAPI, Jinja, HTMX, Plotly) when it is built.
- `git` on the household machine, so a production build can name its commit
  and refuse uncommitted code (ADR-014).
- The existing quality gate: ruff, ty, complexipy, pytest.

## Left to Other Tickets

- **Pull request #57 (issue #8):** ADR-014 must adopt one file per
  publication, or this document's publishing section changes (ADR-015).
- **Issue #11:** the dashboard's screens, its publication picker, and how the
  login page looks.
- **Issue #12:** acceptance cases for restore, retry and profile separation,
  taken from the tables above, and the implementation order.
- **Pull request #45:** the Bronze store moves its schema into
  `migrations/bronze/`, records its profile and stage, and is opened through
  the profile.
