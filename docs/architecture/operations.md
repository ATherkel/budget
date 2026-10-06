---
type: architecture
---
# Operations

Status: accepted ([ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md)).
Resolves [issue #10](https://github.com/ATherkel/budget/issues/10).

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
- [ADR-014](../decisions/ADR-014-gold-publications-and-history.md) and
  [`publications.md`](publications.md): publications in one Gold store,
  recipes, immediate promotion with `undo`, retention, past views, `verify`,
  and the append-only decision log.
- [ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md):
  profiles, one store per ETL stage, legacy publications, development from
  backups, and household inputs as text.

Three principles apply throughout:

- **Production is written only by pipeline commands.** No test, ad hoc SQL
  session, or hand edit writes a production store.
- **Everything a person says is text; everything a bank says is a file.** The
  stores can be rebuilt from the export archive and the inputs folder. Backups
  make that fast, not possible.
- **Financial values reach the operator's terminal, never a log.**

## Stores

Each ETL stage persists its output in its own SQLite store. Kimball and
Caserta's *The Data Warehouse ETL Toolkit* names four steps, *extract*,
*clean*, *conform* and *deliver*, and recommends saving the data after each so
a failure restarts from the last completed step. Here the saved steps are the
stores, and clean and conform share Silver's. Kimball's list of ETL subsystems
groups those two as one, *Cleaning and Conforming*, and Kimball Group leaves
the number of saved copies to the design. The one copy it insists on, the
untransformed extract, is Bronze
([research note](../research/kimball-eccd-and-medallion-layers.md)).

| Store | Step | Holds | Rebuildable from | In a backup set |
| --- | --- | --- | --- | --- |
| `bronze.db` | Extract | Raw payloads, import runs, source records, format failures | The export archive and the import log | Yes |
| `silver.db` | Clean and conform | Canonical transactions, unbooked records, validation errors, import review items, evidence | Bronze and the inputs | Yes, so development can start from it |
| `gold.db` | Deliver | The retained publications' Gold tables and lineage, recipes, configuration snapshots, the current pointer and its history, labels, legacy entries | Results: each from its recipe, replayed with its code (ADR-014). Recipes and the pointer history: no, they are history | Yes |
| `gold/legacy/publication-<id>.db` | Deliver: legacy | One labeled publication that a Gold migration could not convert, in its old schema | Its recipe, replayed with its code | Yes |

Silver's conforming makes the sources agree: it produces source-neutral
canonical records and resolves duplicates. Building and publishing the
conformed dimensions (account, category, date) belongs to Kimball's
*Delivering* group, as the work of its dimension manager. Here Gold builds
them, because they describe the household, not any source.

Rules for every store:

- **Created only by `migrate`.** Each store has its own numbered migrations,
  in `migrations/bronze/`, `migrations/silver/` and `migrations/gold/`, and its
  own `PRAGMA user_version`. Opening a store never creates tables and fails
  when the file does not exist (ADR-013). The migrate runner also creates
  scratch stores and legacy extracts, from the same migration files.
- **It knows its profile and stage.** `migrate` writes `profile` and `stage`
  into a one-row `store_identity` table when it creates the store. Opening a
  store under another profile or as another stage is refused. The one
  exception is development's `upstream/` folder: development opens the
  production stores there read-only, and nowhere else.
- **A write to one store is one transaction.** Silver and Gold commit
  separately. Readers only reach Gold through the pointer, so a crash between
  the two leaves the previous publication current.
- **One writing command at a time.** Every command that writes holds a lock on
  `budget.lock` in the profile's stores folder for its whole run, including
  the backup set it writes. A second writing command exits 4 at once with
  "another command is running". Commands that only read (`status`, `review`,
  `check`, `serve`) take no lock.

### Publishing a Gold build

As [`publications.md`](publications.md#pipeline-builds) defines: in one write
transaction in `gold.db`, the new publication's result is stored, the pointer
moves to it, and the pointer history records the move. **That transaction is
the commit point.** A crash before it commits leaves the previous publication
current and nothing to clean up. Results that are no longer retained (not
current, not previous, not labeled) are deleted by a later transaction.

The dashboard reads the pointer from `gold.db` for each page and pins that
`publication_id` across the page's requests. A page whose publication has
since been deleted gets `PublicationUnavailable` and is offered the current
one (ADR-014). Past views (`view --as-was`, `view --known-at`) are
publications in `gold.db` too, and can never become current. Views, replays
and `verify` work in scratch stores under the profile's `scratch/` folder,
which are deleted afterwards.

Every Gold table holds every retained publication. A query typed by hand
against `gold.db` must filter on `publication_id`, or it adds retained
publications together. Views restricted to the current publication
(`current_*`) are deferred: a later migration can add them if hand queries
become routine.

### Legacy publications

A Gold migration converts the retained results where it can
([`publications.md`](publications.md#retention)). For a labeled result it
cannot convert, `migrate`, before changing the schema:

1. extracts that publication, in its old schema, to
   `gold/legacy/publication-<id>.db`;
2. records a legacy entry in `gold.db`: the `publication_id`, its label, the
   code version that opens it (from its recipe), the extract's path, and the
   pre-migration backup set.

`view` lists legacy entries with the code version to check out and the
extract to open. Retention never deletes a backup set that a legacy entry
names. `unlabel` on a legacy publication deletes its entry and extract and
releases the backup set.

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
  `%APPDATA%\budget\`. They hold paths and settings, no secrets.
- **Test profiles are never files.** The test suite builds each profile in a
  temporary directory and refuses a store path outside it. No test reads
  `imports/`, a profile file, or `BUDGET_PROFILE`
  ([`tdd.md`](../agents/tdd.md)). The suite removes `BUDGET_PROFILE` from the
  environment of every test, and a test that runs the CLI as a subprocess
  passes it an explicit environment, so a value set in the operator's shell
  never reaches a test run.

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

[backups]
keep_all_days   = 14          # every set from the last 14 days
keep_daily_days = 365         # then the newest set of each day
keep_monthly    = "forever"   # then the newest set of each month

[dashboard]
bind = "192.168.1.20"         # reserve this address for the PC in the router
port = 8750
```

A development profile has `profile = "development"`, its own `stores`,
`inbox`, `exports` and `inputs`, all four required in every profile file, and
`upstream_backups` naming production's `backups` folder, which it only reads.
It has no `[backups]` table, because only production writes backup sets. The
inbox and the export archive are separate folders, neither inside the other:
otherwise the archive would hold the inbox file itself, and an import would
remove the only copy.

### Where production lives

```text
%LOCALAPPDATA%\budget\production\      live stores: never cloud-synchronised (ADR-013)
    bronze.db
    silver.db
    gold.db
    gold\legacy\publication-000001.db  only after a Gold migration
    budget.lock                        held by the command that is writing
    recovery-sets.json                 backup sets a failed migration may need
    backup-staging\                    a backup set until it is complete
    scratch\
    logs\
OneDrive\Budget\                       closed files only: safe to synchronise
    inbox\<account_id>\                exports waiting to be imported
    exports\<account_id>\              the export archive
        refused\<hash>\                copies of refused exports, kept for replay
    inputs\                            what the household says
        accounts.toml
        taxonomy.toml
        rules.toml
        decisions.jsonl
        imports.jsonl
    backups\<UTC time>\                backup sets, such as 2026-05-02T18-05-11.120731Z
```

### Development diverges from a stage

`dev refresh` restores production's newest backup set into development's
`upstream/` folder, and marks it read-only. `rebuild --from <stage>` rebuilds
that stage and every later one into development's own stores. The stages
before it are opened from `upstream/`, read-only, and never recomputed.
Because a restored set never changes, those stores are opened with SQLite's
`immutable` flag, so SQLite never tries to create files beside them.

| What changed | Command | Reads from `upstream/` | Writes in development |
| --- | --- | --- | --- |
| Source parsing (Bronze code) | `rebuild --from bronze` | Raw payloads and import runs | `bronze.db` (source records re-derived), `silver.db`, `gold.db` |
| Silver mapping, identity, or a Silver decision | `rebuild --from silver` | `bronze.db` | `silver.db`, `gold.db` |
| Accounts, taxonomy, rules, a classification decision, or Gold code | `rebuild --from gold` | `bronze.db`, `silver.db` | `gold.db` |

Development's inputs are a working copy. `dev refresh --inputs` replaces them
with production's; plain `dev refresh` leaves them alone. A development store
makes no reproducibility promise: it may build from uncommitted code, and
nothing records which code that was (ADR-014).
Production builds refuse uncommitted code, so production runs from its own
clean checkout, separate from the one used for development.

`dev refresh --writable` restores the set into development's own stores
instead of `upstream/`, relabelled as development. It exists to rehearse a
migration on real data: `migrate` then upgrades stores that already hold
production's history, exactly as it will in production (W5). Until the next
plain `dev refresh`, development reads every stage from its own stores.

## Household Inputs

Everything the household authors lives in the inputs folder as text. Every
file:

- is UTF-8, with or without a leading byte-order mark, which some Windows tools
  write;
- carries `format = 1` (TOML) or `"format": 1` on each line (JSON Lines), and
  an unknown format version is refused;
- rejects unknown keys, so a misspelt key is an error, not an ignored line;
- uses durable, lowercase, hyphenated identifiers such as `joint-current`.

The folder holds exactly the five files below. Any other file is a
configuration error that names it: a OneDrive conflict copy such as
`decisions-LAPTOP.jsonl` would otherwise hold decisions that no build reads,
and a stray `rules (1).toml` would hold rules nobody applies.

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
bank_account_number = "1234567890"   # optional; checked against the export filename

[account.joint-savings]
display_name = "Joint savings"
account_type = "savings"
ownership_scope = "household"
currency = "DKK"
source_format = "danske-csv-v1"
# closed_on = 2027-06-30         # set when the account closes
```

`bank_account_number` is optional: the account's number as the bank writes it
in the filenames of its exports. It catches an export saved to the wrong inbox
folder. It is a quoted string, so leading zeros survive, and two accounts may
not declare the same number. Each source format states whether its filenames
carry an account number, where, and in what shape, in its own section of the
Bronze layer (for example
[`danske-csv-v1`](bronze-layer.md#danske-csv-format-danske-csv-v1)). A declared
number of a shape the format's filenames never carry could never match, so it
is a configuration error rather than a refusal of every export. When an export's
filename carries a number, it must match the declared one. A mismatch refuses
that file before Bronze, and the file is never moved to another account
(see [Failure and Retry](#failure-and-retry)). The check reads the filename,
not the content: it does not catch an export the bank labelled with the wrong
account.

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
{"format": 1, "entry": 1, "decision_id": "d-0001", "recorded_at": "2026-04-10T17:02:11Z", "kind": "classify", "targets": ["7c1e0b9a4d2f…"], "category": "gifts", "reason": "Wedding present", "supersedes": []}
{"format": 1, "entry": 2, "decision_id": "d-0002", "recorded_at": "2026-04-11T08:40:37Z", "kind": "pair", "targets": ["3f9a2c1e77b0…", "a04d6e12c9f3…"], "reason": "Settles an ambiguous transfer", "supersedes": []}
{"format": 1, "entry": 3, "decision_id": "d-0003", "recorded_at": "2026-04-12T19:15:02Z", "kind": "retract", "targets": [], "reason": "Was not a gift", "supersedes": ["d-0001"]}
```

The fields and their rules are defined in
[`publications.md`](publications.md#the-decision-log). Kinds: `classify`,
`pair`, `one-sided-transfer` (ADR-011, ADR-012); `void-import-run`,
`same-transaction`, `withdrawn`, `accept-discrepancy` (Silver, issue #5); and
`retract`, which withdraws an earlier decision without replacing it. It is
named `retract` so it is not confused with *withdrawn*, which records that the
bank removed a transaction. A new decision on a target that already has one
must list the old one in `supersedes`, or the boundary rejects it. One entry
can supersede several decisions: a `pair` whose two legs each have their own
`classify` decision lists both. Nothing is edited in place.

The Silver kinds target these:

| Kind | `targets` | Other fields |
| --- | --- | --- |
| `void-import-run` | one `import_run_id` | none |
| `accept-discrepancy` | one `import_run_id` | none |
| `withdrawn` | one `transaction_id` | none |
| `same-transaction` | the existing `transaction_id` | `record`: `{"payload_id": …, "record_ordinal": …}`, the source record that shows it under new text |

Two checks guard the log against edits that bypass `decide`:

- **Every build re-validates every entry** with the boundary's rules below. A
  line added by hand that breaks one, for example a second decision on a
  transaction without `supersedes`, is a configuration error naming the entry.
- **Every recipe records the log position it read** and a SHA-256 of the log
  up to that position. `check` and every build fail when that prefix no longer
  hashes the same, so an edit to an entry a build has read is caught.

Every entry ends with a line feed. A final line without one was cut off by a
crash while it was being written, and is treated as never written: `check` reports it, and `decide`
refuses until the partial line is deleted. No build has read it, so deleting
it is the one safe hand edit. If an earlier entry is ever damaged, copy the
log back from the newest backup set, whose manifest records its length, and
record again the decisions made since.

### `imports.jsonl`: the import log

One line per Bronze import run, mirroring Bronze's `ImportRun` plus the
archive path. It is what makes Bronze rebuildable from the archive, because
the declarations (account, `covers_from`, `covers_through`, `started_at`)
exist nowhere outside Bronze.
Every command that writes Bronze brings it up to date before it finishes, and
`verify` checks that the two agree.

```json
{"format": 1, "import_run_id": "run-0001", "account_id": "joint-current", "source_format": "danske-csv-v1", "archive_path": "joint-current/export-20260402.csv", "payload_sha256": "c0ffee…", "exported_on": "2026-04-02", "exported_on_source": "filename", "covers_from": "2026-03-01", "covers_through": "2026-04-02", "started_at": "2026-04-02T18:03:44.120731+00:00", "outcome": "stored", "repeat_of": null}
```

- **`started_at`** is Bronze's own timestamp, written exactly, with its
  microseconds and offset, so a replay restores the run unchanged.
- **`archive_path`** is relative to the export archive and uses `/`. Its last
  part is the export's original filename. An accepted export, a format failure
  included, is archived as [W1](#w1-the-monthly-import) describes. A refused
  run's bytes are copied to `<account_id>/refused/<first 12 characters of the
  payload hash>/<original filename>`, while the file itself stays in the inbox:
  the account's own folder holds only accepted exports, and replay can still
  restore the refusal. An export named like one of the archive's own folders
  (`refused`, or 12 hexadecimal characters, in any case) goes straight to its
  hash folder. A place an entry names stays reserved for that run's bytes,
  even while its copy is missing, and names that differ only in case are one
  place: other bytes never take it, and a retry of that run, or the next
  refusal of the same file (the same account, name and bytes), writes a
  missing copy back there. Archived
  bytes are never overwritten: when every place a run's export may go already
  holds other bytes, that run is not logged, and every import stops before
  writing anything until the conflicting file is moved aside.
- **Order.** Before an import writes anything of its own, every run Bronze
  holds that the log lacks is archived and logged, oldest first, from the bytes
  Bronze retains. That includes a refused run a crash interrupted, whose file no
  retry would ever finish. Then Bronze commits the new run, its bytes are
  archived, its entry is appended and forced to disk with `fsync`, and only
  then does an accepted export leave the inbox, provided the file still holds
  the bytes that were imported. A file saved over in the meantime stays.
- **Every complete line is the one entry of a run Bronze recorded.** It must
  be, byte for byte, the entry the import writes for that run at one of the
  places its export may be archived. A blank line, a second entry for a run, or an entry that
  disagrees with its run stops the import before it writes; restoring the log
  from the newest backup set is safe, because the next import logs again
  every run Bronze holds. An entry for a run Bronze never recorded means
  Bronze is older than the log. Those entries are then the only record of
  their runs, so the log is never rolled back: Bronze is restored up to it.
- **A cut-off final entry.** Every entry ends with a line feed. A final line
  without one was cut off by a crash. Unlike the decision log's, it is
  completed, never deleted, when Bronze proves what it was going to say: the
  line must begin the entry of a run that is archived but not yet logged. The
  rest of that entry is then appended. A cut-off line no such run proves stops
  the import before it writes, as above.

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
`decision_id` and `recorded_at`, appends the line, forces it to disk with
`fsync`, and returns the entry. A rejection names every reason and records nothing.

The boundary sits in the application layer, not in presentation. The
dashboard stays read-only: it has no route that reaches the boundary.

## Commands

`budget [--profile <file>] <command>`. The CLI uses the standard library's
`argparse`.

| Command | Does | Writes | Publishes |
| --- | --- | --- | --- |
| `migrate [--stage <stage>] [--new-store]` | Creates or upgrades stores. In production, takes a backup set before changing an existing store and another after; a missing production store is started only with `--new-store`, and only when no complete backup set holds one that could restore it. A Gold migration converts retained results, extracts and records legacy publications, then runs a pipeline build (ADR-014). | Store schemas, legacy extracts, backup sets | After a Gold migration |
| `check` | Validates every input file and the decision-log prefix. Never builds. | Nothing | No |
| `import` | Imports each file in the inbox on its own, then rebuilds and publishes what was stored. A refused file stays in the inbox. | Bronze, the import log, Silver, Gold | Yes, if the build succeeds |
| `rebuild [--from bronze\|silver\|gold]` | Rebuilds from a stage; `gold` by default. | Stages from `--from` on | Yes, if the recipe changed |
| `review [--kind <kind>] [--account <id>]` | Lists open review items, Silver's and Gold's, with what a person needs to settle each one. | Nothing | No |
| `decide <kind> <targets…> [options] --reason <text>` | Proposes a manual decision to the boundary, then rebuilds from the stage the decision affects. | The decision log, then stores | Yes |
| `status` | Shows balance and classification completeness (below). | Nothing | No |
| `undo` | Moves the pointer back (ADR-014). | `gold.db` | Pointer only |
| `view --as-was <date> \| --known-at <date> --label <text>` | Builds or finds a past view (ADR-014). Without options, lists retained and legacy publications. | `gold.db`, through a scratch store | Never current |
| `label <publication_id> <text>` / `unlabel …` | Keeps a result beyond the retention rule, or stops keeping it. | `gold.db` | No |
| `backup` | Writes a backup set of production and names it. Also runs automatically; see below. | The backups folder | No |
| `restore [<backup set>]` | Restores the newest complete set, or the one named, into an empty profile, catches up with the import log, then runs `verify`. | Every store | Yes, if it caught up |
| `restore --from-archive` | Last resort: rebuilds Bronze from the archive and the import log, then Silver and Gold. | Every store | Yes |
| `verify` | Checks integrity, and replays the current publication's recipe to prove it reproduces (ADR-014). | `scratch/` only | No |
| `dev refresh [--inputs] [--writable]` | Development only: restores production's newest complete backup set into `upstream/`, or with `--writable` into development's own stores. | Development only | No |
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
| 1 | Unexpected error: a defect. Python's own exit status for an unhandled exception. |
| 2 | Usage error. `argparse`'s own exit status. |
| 3 | Refused input: a configuration error, a rejected decision, a misfiled export, or an import run Bronze refused. `import` still publishes the files it stored. |
| 4 | Refused environment: no profile, a store from another profile or stage, a missing or newer migration, SQLite below the version floor, uncommitted code in production, running code other than the code version a replayed recipe names (ADR-014), another writing command running, a store locked past its busy timeout, or `restore` into a profile that has stores. |
| 5 | Verification failed: a fingerprint mismatch, a failed integrity check, a backup set whose checksums do not match its manifest, or an import log that disagrees with Bronze. |

The codes 1 and 2 are the ones Python and `argparse` already use, so every
path out of the program means what the table says.

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
  transactions  2026-04-01 … 2026-05-01, 58 source records
  Enter the range you asked the bank for, from: 2026-04-01  through: 2026-05-02
joint-savings   export-20260502.csv
  exported on   2026-05-02 (from filename)
  transactions  2026-01-31 … 2026-01-31, 1 source record
  Enter the range you asked the bank for, from: 2026-01-01  through: 2026-04-30
Import both? [y/N] y
Bronze   2 import runs stored
Silver   2 admitted, 0 quarantined
Gold     publication 43 is current (was 42)
Changes  April: income +12,000.00, expenses +3,450.00, unclassified out +1,000.00
Review   1 unmatched-transfer, 0 other
Backup   2026-05-02T18-05-11Z written
```

Bronze requires the declared range on every export, and never infers it from
the filename, the payload or the export date
([`bronze-layer.md`](bronze-layer.md)). It matters most for the savings
export: its last transaction is in January, and only the declaration says that
February to April were quiet rather than never exported. Each file then moves
to `exports\<account_id>\` under its original name, which carries the export
date. When that name is already taken by different bytes, or is the name of
one of the archive's own folders, it goes to
`exports\<account_id>\<first 12 characters of the payload hash>\` instead. A
refused export stays in the inbox, and a copy of its bytes goes to
`exports\<account_id>\refused\<first 12 characters of the payload hash>\`
([`imports.jsonl`](#importsjsonl-the-import-log)).

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

1. In development: `dev refresh --writable`, then `migrate`. The stores now
   hold production's real history, so `migrate` upgrades existing data exactly
   as it will in production, including any legacy extraction and the build
   that follows. Its printed diff must show only what the migration intends.
2. In production: `migrate`, which writes a backup set first, converts the
   retained results, extracts and records any legacy publication, runs a
   pipeline build (ADR-014), and writes a backup set after. Then `verify`.

### W6: the machine dies

On the new machine: install the code version the newest backup set's manifest
names, write the production profile, run `budget restore`, then
`budget serve`. `restore` takes the newest complete set, replays every import
that the live `imports.jsonl` lists beyond the set, from the export archive,
rebuilds with any decisions recorded since, and runs `verify`. Nothing is
missing, provided OneDrive had synchronised the inputs folder and the export
archive.

### W7: every backup set is lost

`budget restore --from-archive` rebuilds Bronze from the export archive and
`imports.jsonl`, then Silver and Gold from the inputs. Reports come back
exactly. Recipes, past views and legacy publications are lost, because they
live only in `gold.db`, `gold\legacy\` and their backups.

## Failure and Retry

| Failure | Effect | Retry |
| --- | --- | --- |
| Configuration error, including an unknown file in the inputs folder | Nothing is built; exit 3 | Fix or remove the file and rerun |
| Refused import run (account conflict, or a declared range that starts after it ends, ends after the export date, or leaves out one of the payload's transactions) | Recorded as refused and logged, with a copy of its bytes under `exports\<account_id>\refused\`; the file stays in the inbox; the other files are stored and published; exit 3 | Move the file or correct the declaration, then rerun |
| Misfiled export (the filename's account number is not the account's declared `bank_account_number`) | Rejected before Bronze: no import run is recorded and nothing reaches the import log; the file stays in the inbox; the other files are stored and published; exit 3 | Move the file to the right account's folder, or fix the declaration, then rerun |
| Format failure | Stored with its `FormatFailure`; Silver quarantines it; the file is archived | Settled by a parser fix and `rebuild --from bronze` |
| Crash during an import | Each file is idempotent: a file whose account, original filename and payload hash already have a `stored` or `repeat` run is finished (archived, logged once, and removed from the inbox) without a new run. Any other run Bronze holds but the log lacks is archived and logged by the next import | Rerun `import` |
| The archive holds other bytes, a file where a folder must go, or a place reserved for other bytes, everywhere a run's export may go | Nothing is overwritten; the run stays in Bronze but is not logged; every import stops before writing, naming the account and the run | Move the conflicting archive file aside, then rerun |
| An inbox file is saved over while it is imported | The run for the bytes that were read is stored, archived and logged; the new file stays in the inbox | Rerun `import` |
| An inbox file is removed while it is imported | The import finishes from the bytes it read; there is nothing left to remove | Nothing to do |
| An import-log entry cut off by a crash | The next import completes it from the run Bronze holds | Nothing to do |
| The import log holds a blank, unreadable or second line for a run, or an entry that does not restate its run exactly | The import stops before writing anything | Restore `imports.jsonl` from the newest backup set; the next import logs again every run Bronze holds |
| The import log mirrors a run Bronze never recorded | Bronze is older than the log; the import stops before writing anything | Restore Bronze up to the log; never roll the log back |
| A logged run's archived copy is saved over, and the run's file is presented again | Nothing is overwritten; the run stays logged and the file stays in the inbox; other imports go on | Put the run's own export back where its log entry says, then rerun |
| An inbox file is held open by another program | The import is finished; the file stays in the inbox | Close the program, then rerun `import`: the file is removed as a retry |
| Crash during a build | SQLite rolls back the uncommitted publication; the previous publication stays current | Rerun the command |
| Another writing command is running | Exit 4 at once; nothing is written | Rerun when the other command ends |
| A decision-log line cut off by a crash | `check` reports it; `decide` refuses | Delete the partial last line |
| Crash while writing a backup set | The set stays in `backup-staging\` or as a `.partial` folder, is never used, and is deleted by the next backup | Nothing to do |
| The backup before a migration cannot be written or verified | The migration does not begin; the schema and its version are unchanged; exit 4, or 5 when a copy or the import log does not verify | Fix what the message names, then rerun `migrate` |
| A migration fails | No step of it is committed and the store keeps its version, though a stage migrated before it (Bronze, before Silver) keeps its new one; the set taken first stays held for recovery until a migration succeeds | Fix the defect; the held set restores the stores if needed |
| The backup after a migration fails | The store is migrated; the set taken first stays held; exit 4, saying so | Fix what the message names, then run `budget backup` |
| `migrate` finds no production store for a stage | Nothing is created or changed, in any stage; exit 4 | Restore the newest backup set that holds it, or, for a first store, rerun with `--new-store`, adding `--stage` for that stage alone when the other stage's store exists |
| OneDrive offline | Complete backup sets wait in the local OneDrive folder | Nothing to do |

A genuine repeat export has a new export date in its filename, so it is
presented to Bronze as a new `repeat` run, as the Bronze rules require.

## Backup and Restore

- **A backup set** is a folder under `backups\<UTC time>\`, named to the
  microsecond with `-` for `:`, such as `2026-05-02T18-05-11.120731Z`. It
  holds a snapshot of every store taken through SQLite's backup API, a copy of
  every file in the inputs folder under `inputs\`, and `manifest.json`. The
  export archive is not copied, because Bronze holds each payload's bytes.
  Until Gold has a store, a set holds `bronze.db` and, once the profile has
  one, `silver.db`, and a backup is refused while the stores folder holds any
  other store: `gold.db`, a `gold\` folder, or any other SQLite file. A set
  without it would claim to be a complete copy of the profile. A set written
  before sets covered Silver holds `bronze.db` alone, in the same manifest
  format: it stays complete, retention treats it as any other set, and since
  it holds no Silver store, it never stops `migrate --new-store` starting one.
- **The manifest** records, in this order:

  ```json
  {
    "format": 1,
    "profile": "production",
    "created_at": "2026-05-02T18:05:11.120731+00:00",
    "code_version": {"package": "0.1.0", "source_sha256": "9f2c…"},
    "stores": {
      "bronze": {"path": "bronze.db", "schema_version": 1},
      "silver": {"path": "silver.db", "schema_version": 1}
    },
    "logs": {"imports.jsonl": 1730, "decisions.jsonl": 0},
    "files": {
      "bronze.db": {"sha256": "c0ffee…", "bytes": 81920},
      "silver.db": {"sha256": "beefed…", "bytes": 90112},
      "inputs/accounts.toml": {"sha256": "5ca1ab…", "bytes": 412},
      "inputs/imports.jsonl": {"sha256": "0ddba1…", "bytes": 1730}
    }
  }
  ```

  `logs` gives each log's length in bytes, counting complete lines only: a
  final line a crash cut off is not an entry yet. A log that does not exist
  has length 0. `code_version` is the package version and a SHA-256
  fingerprint of its source: one line per `.py` and `.sql` file in the
  installed `budget` package, sorted, each its `/`-separated path, a tab, its
  SHA-256 and a line feed. Any checkout can be compared with it, with or
  without git.
- **The snapshot and the import log agree.** Every complete entry of the
  copied `imports.jsonl` must restate, byte for byte, a run in the snapshot,
  as an import checks before it writes. A blank, damaged or second entry, or
  one for a run the snapshot lacks, refuses the set with exit 5. Runs the log
  does not mention yet, and a cut-off final line, are what the next import
  logs and completes, so they are backed up as they are.
- **When:** in production, before a `migrate` that changes an existing
  store, and after every `migrate` that changed anything, a new store
  included; and by `budget backup`. A `migrate` that changes both Bronze and
  Silver takes one set before the first change and one after the last. A
  migration that changes nothing writes no set. Only production writes backup sets. Nothing imports into production
  until the `import` command backs up after its Bronze writes: until then,
  `BronzeStore.import_file` and `import_inbox_file` refuse the production
  profile.
- **Written whole or not at all.** A set is written into the profile's local
  `backup-staging\` folder, `manifest.json` last. It is then copied into the
  backups folder as `<name>.partial`, every copy is checked against the
  manifest, and only then is it renamed to its name. A set under its name
  never replaces another. A set without a manifest, or whose files do not
  match its checksums, is incomplete: it is never selected, and `restore` and
  `dev refresh` take the next newest. A failure removes what it staged; what
  a crash leaves in `backup-staging\`, or as a `.partial` folder, the next
  backup deletes. A folder under a set's own name is never deleted that way,
  even without a manifest.
- **Kept**, by the `[backups]` keys in the production profile: every set from
  the last `keep_all_days` (14) days, then the newest set of each day for
  `keep_daily_days` (365) days, then the newest set of each month for
  `keep_monthly` months, counting the current one, or for good with
  `"forever"`, the default. Days and months are UTC, as set names are. Each
  backup prunes after it is published, and keeps itself whatever the keys
  say. Retention reads only manifests, never every set's files. It deletes a
  set by renaming it to `<name>.partial` first, and a deletion that fails is
  left to the next backup. Each set is a full copy of every store, so a year
  of daily sets can take a few gigabytes; the keys are there to tune that.
- **Never pruned:** a set whose manifest format this code does not read,
  since a later version may record a reason to keep it, such as a legacy
  entry (none exist before Gold has a store); and every set held for
  recovery. A `migrate` holds the set it takes first in `recovery-sets.json`
  beside the stores, and releases it once a migration succeeds and its own
  set is written. A failed or interrupted migration therefore keeps its set
  however small the keys are, until a migration succeeds. A later backup
  also releases a held set once any store it records is at an older schema
  version than the new set's, since the migration it was taken for has
  committed. While that file cannot be read, nothing is pruned.
- **Where:** OneDrive, which is safe for them: a backup set is closed files,
  unlike a live database with its WAL files (ADR-013).
- **`restore`** writes only into a profile with no stores. It takes the newest
  complete set unless one is named, checks every SHA-256 against the
  manifest, runs `PRAGMA integrity_check`, and migrates stores older than the
  code. It then catches up: it uses the live inputs folder, or the set's copy
  when the live one is missing, replays every `imports.jsonl` line beyond the
  length the manifest recorded, taking each file from the export archive, and
  rebuilds if anything was replayed or decided since. Finally it runs `verify`.
- **`verify`** runs `PRAGMA integrity_check` on every store, then replays the
  current publication's recipe from Bronze in a scratch store and compares the
  result fingerprint with the recorded one. It refuses to run when the running
  code is not the code version the recipe names
  ([`publications.md`](publications.md#verify)). It also checks that the
  import log agrees with Bronze and that the decision-log prefix hashes match.

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
- The dashboard opens `gold.db` read-only and is given no other store's
  path. It has no route that writes, apart from login and logout.
- The production address is fixed in the profile, so reserve it for the PC in
  the router; otherwise `serve` fails to start when the router hands out
  another one.
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
| `migrate` | Every migration from empty, and from the previous release's fixture stores | Rehearsed after `dev refresh --writable`, on production's real data, before production |
| Import and its retry | Idempotent rerun, and a crash injected after each step | Real exports' shapes, through `upstream` |
| Publishing | Crash before and after the commit point; `undo`; retention deletion | Every `rebuild` publishes |
| Legacy publications | A Gold migration that cannot convert a labeled result: extract, legacy entry, and a backup set that retention keeps | With the migration's rehearsal |
| Backup and restore | Backup, restore into an empty profile, `verify`; a set cut off before its manifest is skipped; `restore` replays imports logged after the set | Every `dev refresh` is a restore |
| `restore --from-archive` | Rebuilds the fixtures' reports exactly | Once before it is first trusted, then yearly |
| Log redaction | Asserted on every walkthrough | — |
| Profile guards | Every refusal: no profile, wrong profile, a production store outside `upstream/`, test path outside the temporary directory, a second writing command | — |
| Decision log | A hand-added line that breaks a rule; an edited prefix; a cut-off last line | — |

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

- **Issue #11:** the dashboard's screens, its publication picker, and how the
  login page looks.
- **Retry and profile separation:** their acceptance cases, taken from
  *Failure and Retry* and *Profiles*, belong to the first dashboard release's
  store and pipeline-build issues, which the readiness review (issue #12)
  created.
- **Restore and `dev refresh`:** their acceptance cases, taken from the tables
  above, belong to the issue that builds them; the readiness review (issue
  #12) moved them out of the first dashboard release.
- **The `import` command:** it backs up after its Bronze writes. Until it
  does, nothing imports into production.
- **Pull request #45:** the Bronze store moves its schema into
  `migrations/bronze/`, records its profile and stage, and is opened through
  the profile.
