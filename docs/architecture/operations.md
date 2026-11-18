---
type: architecture
---
# Operations

## Summary

- How the household runs the pipeline: files, profiles, inputs, commands,
  failures, backup and restore. Every example is synthetic.
- Decisions: [ADR-013](../decisions/ADR-013-sqlite-store-integer-minor-units.md),
  [ADR-014](../decisions/ADR-014-gold-publications-and-history.md) with
  [`publications.md`](publications.md), and
  [ADR-015](../decisions/ADR-015-profiles-stages-and-household-inputs.md).
- Only pipeline commands write production. A person's words are text and a
  bank's are files, so the archive and inputs rebuild every store.
- Financial values reach the terminal, never a log.

## Stores

The stores follow Kimball and Caserta's four ETL steps (*extract*, *clean*,
*conform*, *deliver*), and the project is a deliberate test of that theory.
Saving the data after each step lets a failure restart from the last one
completed. Clean and conform share Silver's store, as Kimball's subsystems
group them, and Bronze is the untransformed extract Kimball insists on keeping
([research note](../research/kimball-eccd-and-medallion-layers.md)).

| Store | Step | Holds | Rebuildable from | In a backup set |
| --- | --- | --- | --- | --- |
| `bronze.db` | Extract | Raw payloads, import runs, source records, format failures | The export archive and the import log | Yes |
| `silver.db` | Clean and conform | Canonical transactions, unbooked records, validation errors, import review items, evidence, and ADR-020's fingerprint and completion provenance | Bronze and the inputs | Yes, so development can start from it |
| `gold.db` | Deliver | Retained publications' Gold tables and lineage, recipes with their Silver provenance, configuration snapshots, the current pointer and its history, labels, legacy entries | Results: each from its recipe, replayed with its code (ADR-014, ADR-020). Recipes and pointer history: no, they are history | Yes |
| `gold/legacy/publication-<id>.db` | Deliver: legacy | One labeled publication a Gold migration could not convert, in its old schema | Its recipe, replayed with its code | Yes |

Silver conforms the sources: source-neutral records, duplicates resolved. The
conformed dimensions (account, category, date) are Kimball's dimension
manager's work in *Delivering*, so Gold builds them: they describe the
household, not a source.

Rules for every store:

- **Created only by `migrate`**, from its own numbered migrations in
  `migrations/bronze/`, `silver/` or `gold/`, with its own
  `PRAGMA user_version`. The migrations ship in the wheel and sdist. Opening a
  store never creates tables and fails when the file is missing (ADR-013). The
  same runner creates scratch stores and legacy extracts.
- **It knows its profile and stage**, from a one-row `store_identity` table
  `migrate` writes. Opening it under another profile or stage is refused,
  except that development opens production's stores read-only in `upstream/`.
- **A write to one store is one transaction.** Silver and Gold commit
  separately ([Silver's boundary](silver-layer.md#build-provenance)). Readers
  reach Gold only through the pointer, so a crash between stages leaves the
  previous publication current.
- **One writing command at a time.** A writing command holds `budget.lock` in
  the stores folder for its whole run, its backup set included. A second one
  exits 4 at once with "another command is running". `status`, `review`,
  `check`, `serve` and `suggest-rules` only read and take no lock.

### Publishing a Gold build

In one `gold.db` transaction the new result is stored, the pointer moves to it
and the pointer history records the move
([`publications.md`](publications.md#pipeline-builds)). **That transaction is
the commit point**: a crash before it leaves the previous publication current
and nothing to clean up. A later transaction deletes results no longer
retained.

The dashboard reads the pointer for each page and pins that `publication_id`
across the page's requests; a page whose publication was deleted gets
`PublicationUnavailableError` and is offered the current one (ADR-014). Past
views (`view --as-was`, `view --known-at`) are publications that never become
current. Views, replays and `verify` work in scratch stores under `scratch/`,
deleted afterwards.

Every Gold table holds every retained publication, so a hand query must filter
on `publication_id`.

### Provenance recovery

[Silver build provenance](silver-layer.md#build-provenance) defines what
Silver stores, and [Gold acceptance](publications.md#gold-acceptance) when Gold
may publish. The operator's actions:

| Observed state | Action |
| --- | --- |
| Silver reports unbuilt, for example after a pre-provenance migration | Run `budget rebuild --from silver`, then retry the Gold command. |
| Stale decision prefix, effective Silver decisions, or consumed currency | Run `budget rebuild --from silver`; if the account registry is the cause, fix that first. |
| A consumed account is missing from `accounts.toml` | Declare it again, with `closed_on` where appropriate, and retry. A Silver rebuild cannot repair it. |
| Unknown provenance | Do not publish. Rebuild Silver from the known inputs, then retry. |
| Incompatible provenance or contract | Do not publish. Use compatible code or a matching backup set; never infer or edit provenance. |
| Fresh | Continue the Gold build. |

Gold-only decisions, Gold configuration and an added empty account need no
Silver rebuild. `rebuild --from bronze` parses again with the installed parser;
it does not replay a historical one.

### Legacy publications

A Gold migration converts the retained results it can
([`publications.md`](publications.md#retention)). For a labeled result it
cannot convert, `migrate` first extracts it, in its old schema, to
`gold/legacy/publication-<id>.db`, and records a legacy entry in `gold.db`:
the `publication_id`, its label, the code version that opens it, the extract's
path and the pre-migration backup set.

`view` lists legacy entries with the code version to check out and the extract
to open. Retention never deletes a backup set a legacy entry names. `unlabel`
on a legacy publication deletes its entry and extract and releases the set.

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
| Dashboard | Home network or a [private tailnet](#away-from-home), with a passphrase | This PC only | Not served; tested in-process |

### Selecting a profile

- `budget --profile <file> …`, or `BUDGET_PROFILE` naming the file. With
  neither, every command refuses: a default would be production, and a test
  run inherits the operator's shell.
- Profile files live outside the repository, such as in `%APPDATA%\budget\`.
  They hold paths and settings, no secrets, as UTF-8 with or without a
  byte-order mark. Nothing in them is expanded, so every path is absolute.
- **Test profiles are never files.** The suite builds each one in a temporary
  directory and, on each access, refuses any derived path that resolves outside it, symlinks
  included. No test reads `imports/`, a profile file or `BUDGET_PROFILE`
  ([`tdd.md`](../agents/tdd.md)): the suite clears `BUDGET_PROFILE` for every
  test, and a CLI subprocess gets an explicit environment.

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

[gold]
late_booking_days = 7         # days after a month ends before an export settles it

[dashboard]
passphrase_file = 'C:\Users\household\AppData\Roaming\budget\production-passphrase'
bind = "192.168.1.20"         # reserve this address for the PC in the router
port = 8750
```

Every profile file needs `stores`, `inbox`, `exports` and `inputs`. A
development profile has `profile = "development"`, its own four paths, and
`upstream_backups` naming production's `backups` folder, which it only reads;
it has no `[backups]` table, because only production writes sets. The inbox
and the export archive may not nest, or an import would archive the inbox file
and remove the only copy. Production's backups folder may not overlap the
four.

`[gold] late_booking_days` is the late-booking window: how many days after a
month ends an export must be produced to settle the month's late bookings
([`gold-layer.md`](gold-layer.md#late-bookings-settled)). It is a whole number
from 0 to 366, default 7; 0 lets an export from the month's last day settle it,
and a larger value is refused as a typo. The test profile uses the default.
The window is part of each recipe
([`publications.md`](publications.md#the-recipe)), so a change applies from the
next publication.

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

`dev refresh` restores production's newest complete backup set this code can
use into development's `upstream/` folder, read-only. `rebuild --from <stage>`
rebuilds that stage and every later one into development's own stores, and
opens the earlier stages from `upstream/`, never recomputing them. A restored
set never changes, so they open with SQLite's `immutable` flag, which creates
no files beside them.

| What changed | Command | Reads from `upstream/` | Writes in development |
| --- | --- | --- | --- |
| Source parsing (Bronze code) | `rebuild --from bronze` | Raw payloads and import runs | `bronze.db` (source records re-derived), `silver.db`, `gold.db` |
| Silver mapping, identity, or a Silver decision | `rebuild --from silver` | `bronze.db` | `silver.db`, `gold.db` |
| Accounts, taxonomy, rules, a classification decision, or Gold code | `rebuild --from gold` | `silver.db` | `gold.db` |

Development's inputs are a working copy that plain `dev refresh` leaves alone.
`dev refresh --inputs` replaces them with production's before touching any
store, so a failure there changes no store. A development store
promises no reproducibility: it may build from uncommitted code (ADR-014).
Production refuses uncommitted code, so it runs from its own clean checkout.

`dev refresh --writable` restores the set into development's own stores,
relabelled as development, to rehearse a migration on real data (W5). It
leaves `upstream/` alone. A refresh killed part-way can leave stores in
`stores/writable-replaced`, which the next `--writable` refresh deletes.

## Household Inputs

Everything the household authors is text in the inputs folder. Every file:

- is UTF-8, with or without a byte-order mark;
- carries `format = 1` (TOML) or `"format": 1` on each line (JSON Lines), and
  an unknown version is refused;
- rejects unknown keys, so a misspelt key is an error;
- uses durable, lowercase, hyphenated identifiers such as `joint-current`.

The folder holds exactly the five files below; any other file is a
configuration error naming it, so a OneDrive conflict copy such as
`decisions-LAPTOP.jsonl` cannot hold decisions no build reads.

**Amounts are quoted decimal strings**, such as `"-1000.00"`: TOML reads an
unquoted `1000.00` as a float, so an unquoted amount is a configuration error.

The files' history is the configuration snapshots in recipes (ADR-014) and
OneDrive's version history, not git: a `.git` folder in a synchronised folder
risks the inconsistent copies ADR-013 keeps the stores away from.

### `accounts.toml`

The account registry: only accounts inside the reporting boundary.

```toml
format = 1

[owners]                         # owner ID = display name, in display order
household = "Fælles"
alex = "Alex"

[account.joint-current]
display_name = "Joint current"
account_type = "current"         # current | savings
ownership_scope = "household"    # household | person
owner = "household"              # an owner declared in [owners]
currency = "DKK"
source_format = "danske-csv-v1"  # what its inbox folder receives
bank_account_number = "1234567890"   # optional; checked against the export filename

[account.joint-savings]
display_name = "Joint savings"
account_type = "savings"
ownership_scope = "household"
owner = "household"
currency = "DKK"
source_format = "danske-csv-v1"
# closed_on = 2027-06-30         # set when the account closes
```

`[owners]` lists the household's owners, ID to display name, in the order
reports show them. Every account names one of them as `owner`; a missing or
undeclared owner is refused with the account's ID
([Owner](../CONTEXT.md#accounts-and-boundary)).

`bank_account_number` is the account's number as the bank writes it in export
filenames, a quoted string so leading zeros survive; two accounts may not
share one. It catches an export saved to the wrong inbox folder: when a
filename carries a number, it must match, or that file is refused before
Bronze and never moved to another account ([Failure and Retry](#failure-and-retry)).
It reads the filename only, so it cannot catch an export the bank labelled
wrongly. Each source format says whether and how its filenames carry a number
(for example [`danske-csv-v1`](bronze-layer.md#danske-csv-format-danske-csv-v1));
a declared number of a shape the format never carries is a configuration
error.

An account is retired by setting `closed_on`, never by deleting its entry.
Deleting the entry of an imported account is a configuration error: the Gold
build refuses, naming each account Silver holds transactions for that the
registry lacks, and the current publication stays. Restore the entry and
rebuild.

`closed_on` ends the account's managed period
([`MonthlyBalanceSnapshot`](gold-contract.md#monthlybalancesnapshot)). It may
not fall before the account's latest booked transaction; one on the closing
date is allowed. The Gold build checks this first: a `closed_on` too early is a
configuration error naming the account, the date and its latest transaction
date, nothing is built, and the command exits 3 ([Exit codes](#exit-codes)).
Correct the date; the build never drops transactions.

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

[group.home]
name = "Home"
direction = "expense"

[category.furniture]
name = "Furniture"
group = "home"
```

A rename or regroup is also recorded in
[`category-changes.md`](../domains/category-changes.md).

### `rules.toml`

One `[[rule]]` block per classification rule. Every `when` condition must hold,
and `then` has exactly one outcome.

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
`priority` defaults to 0. How rules apply is in
[`classification.md`](classification.md#classification-rules). The transfer
matching window (3 days) is a code constant and enters recipes through the
code version.

### `decisions.jsonl`: the decision log

The append-only log of manual decisions (ADR-014), one JSON object per line,
written only by `budget decide`. It is JSON Lines because the application
writes it, and the standard library writes JSON but not TOML. A missing log, or
one holding only a byte-order mark and whitespace, means no decisions. An
invalid entry refuses a build with exit 3, naming the entry but never its text.

```json
{"format": 1, "entry": 1, "decision_id": "d-0001", "recorded_at": "2026-04-10T17:02:11Z", "kind": "classify", "targets": ["7c1e0b9a4d2f…"], "category": "gifts", "reason": "Wedding present", "supersedes": []}
{"format": 1, "entry": 2, "decision_id": "d-0002", "recorded_at": "2026-04-11T08:40:37Z", "kind": "pair", "targets": ["3f9a2c1e77b0…", "a04d6e12c9f3…"], "reason": "Settles an ambiguous transfer", "supersedes": []}
{"format": 1, "entry": 3, "decision_id": "d-0003", "recorded_at": "2026-04-12T19:15:02Z", "kind": "retract", "targets": [], "reason": "Was not a gift", "supersedes": ["d-0001"]}
```

[`publications.md`](publications.md#the-decision-log) owns the fields, which
kinds collide, and `supersedes`. `entry` is the line number from 1, and
`recorded_at` is UTC to the second. `retract` withdraws an earlier decision
without replacing it; it is not *withdrawn*, which records that the bank
removed a transaction. Nothing is edited in place.

| Kind | Stage | `targets` | Other fields |
| --- | --- | --- | --- |
| `void-import-run` | Silver | one `import_run_id` | none |
| `accept-discrepancy` | Silver | one `import_run_id` | none |
| `withdrawn` | Silver | one `transaction_id` | none |
| `same-transaction` | Silver | the existing `transaction_id` | `record`: `{"payload_id": …, "record_ordinal": …}`, the source record that shows it under new text |
| `classify` | [Gold](classification.md#manual-decisions) | one `transaction_id` | exactly one of `category`, a category ID, or `"adjustment": true` |
| `pair` | [Gold](classification.md#manual-decisions) | two `transaction_id`s | none |
| `one-sided-transfer` | [Gold](classification.md#manual-decisions) | one `transaction_id` | `counterpart_account_id`: the counterpart Gold account |
| `retract` | either | none | none; `supersedes` lists at least one decision |

Two checks catch edits that bypass `decide`:

- **Every build re-validates every entry** against
  [the boundary's rules](#the-validation-boundary-for-decisions); a hand-added
  line that breaks one is a configuration error naming the entry.
- **Every recipe records the log position it read** and a SHA-256 of the log up
  to it. `check` and every build fail when that prefix hashes differently.

Every entry ends with a line feed. A final line without one was cut off by a
crash and counts as never written: `check` reports it and `decide` refuses
until it is deleted, the one safe hand edit. If an earlier entry is damaged,
copy the log back from the newest backup set and record again the decisions
made since; `restore` stops on a damaged log rather than replace it.

### `imports.jsonl`: the import log

One line per Bronze import run, mirroring Bronze's `ImportRun` plus the archive
path. It makes Bronze rebuildable from the archive, because the declarations
(account, `covers_from`, `covers_through`, `started_at`) exist nowhere else.
Every command that writes Bronze brings it up to date before it finishes, and
`verify` checks the two agree.

```json
{"format": 2, "import_run_id": "run-0001", "account_id": "joint-current", "source_format": "danske-csv-v1", "archive_path": "joint-current/export-20260402.csv", "payload_sha256": "c0ffee…", "exported_on": "2026-04-02", "exported_on_source": "filename", "covers_from": "2026-03-01", "covers_through": "2026-04-02", "started_at": "2026-04-02T18:03:44.120731+00:00", "outcome": "stored", "repeat_of": null, "refusal_reasons": []}
```

- **`refusal_reasons`** lists a refused run's
  [refusal codes](bronze-layer.md#rules), and is empty for every other run.
  Replay and the import also accept format 1 lines, which carry no codes: a
  refused run from one reads as `legacy-unrecorded`.
- **`started_at`** is Bronze's own timestamp, exact to the microsecond and
  offset, so a replay restores the run unchanged.
- **`archive_path`** is relative to the archive, with `/`, and ends in the
  export's original filename. An accepted export goes to
  `<account_id>/<original filename>`, or to
  `<account_id>/<first 12 characters of the payload hash>/` when that name
  holds other bytes or is one of the archive's own folder names (`refused`, or
  12 hexadecimal characters, in any case). A refused run's bytes are copied to
  `<account_id>/refused/<hash prefix>/<original filename>` while the file stays
  in the inbox. A place an entry names stays reserved for that run's bytes,
  even while its copy is missing, and names differing only in case are one
  place; a retry, or the next refusal of the same file, writes a missing copy
  back. Archived bytes are never overwritten: when every place a run may go
  holds other bytes, the run is not logged and every import stops before
  writing until the conflict is moved aside.
- **Order.** Before an import writes anything of its own, every run Bronze
  holds that the log lacks is archived and logged, oldest first, from Bronze's
  bytes; that includes a refusal a crash interrupted. Then Bronze commits the
  new run, its bytes are archived, its entry is appended and `fsync`ed, and
  only then does an accepted export leave the inbox, if the file still holds
  the imported bytes.
- **Every complete line is the one entry of a run Bronze recorded**, byte for
  byte as the import writes it for one of the run's archive places. A blank
  line, a second entry for a run, or one that disagrees with its run stops the
  import before it writes; restore the log from the newest backup set, and the
  next import logs every run again. An entry for a run Bronze never recorded
  means Bronze is older than the log, which is then the only record of those
  runs: restore Bronze up to it, never roll the log back.
- **A cut-off final entry** is completed, unlike the decision log's: when its
  text begins the entry of a run that is archived but not yet logged, the rest
  is appended. Any other cut-off line stops the import before it writes.

## The Validation Boundary for Decisions

Every manual decision passes one application boundary before it is recorded,
from the CLI now and from a browser editor later.

```python
class DecisionLog(Protocol):
    def propose(self, proposal: DecisionProposal) -> Recorded | Rejected: ...
    def entries(self) -> Sequence[DecisionEntry]: ...
```

`propose` checks the proposal against the configuration and the current
publication: the targets and category exist, the kind applies (a `pair`'s
amounts cancel), and no other effective decision targets the transaction
unless this one supersedes it. It then sets `entry`, `decision_id` and
`recorded_at`, appends the line, `fsync`s it, and returns the entry. A
rejection names every reason and records nothing. The boundary is in the
application layer; the dashboard has no route to it.

## Commands

`budget [--profile <file>] <command>`, or `python -m budget`, parsed with
`argparse`. Every command except `demo` needs a profile.

| Command | Does | Writes | Publishes |
| --- | --- | --- | --- |
| `migrate [--stage <stage>] [--new-store]` | Creates or upgrades stores. Production takes a backup set before changing an existing store and after. A missing production store starts only with `--new-store`, and only when no complete backup set holds one to restore. A Gold migration converts retained results, records legacy publications, then runs a pipeline build (ADR-014). | Store schemas, legacy extracts, backup sets | After a Gold migration |
| `check` | Validates every input file and the decision-log prefix. Never builds. | Nothing | No |
| `import [--ranges <file>]` | Imports each inbox file on its own, then rebuilds and publishes what was stored. A refused file stays in the inbox. Asks each file's declared range, or reads a ranges file ([W1](#w1-the-monthly-import)). A payload the inbox holds under several accounts is refused ([Failure and Retry](#failure-and-retry)). | Bronze, the import log, Silver, Gold | Yes, if the build succeeds |
| `rebuild [--from bronze\|silver\|gold]` | Rebuilds from a stage; `gold` by default. Never creates an import run or log entry. | Stages from `--from` on | Yes, if the recipe changed |
| `review [--kind <kind>] [--account <id>]` | Lists open review items, Silver's and Gold's, then quarantined import runs no item shows. | Nothing | No |
| `suggest-rules [--out <folder>]` | Lists Silver's bank category pairs with count, sum and any rule covering it. `--out` also writes `taxonomy-draft.toml` and `rules-draft.toml` to edit and copy into `inputs`. | The two drafts, none when Silver has no pair | No |
| `decide <kind> <targets…> [options] --reason <text>` | Proposes a manual decision to the boundary, then rebuilds from the stage it affects. | The decision log, then stores | Yes |
| `status` | Shows [completeness](#completeness-outputs). | Nothing | No |
| `find <text> [--month YYYY-MM] [--account <id>]` | Searches the current publication's transactions, ignoring case, printing each one's handle and category or `category unclassified`. Refused whole when a match is absent from current Silver, as after an `undo`; `rebuild` fixes that. | Nothing | No |
| `undo` | Moves the pointer back (ADR-014). | `gold.db` | Pointer only |
| `view --as-was <date> \| --known-at <date> --label <text>` | Builds or finds a past view (ADR-014). Without options, lists retained and legacy publications. | `gold.db`, through a scratch store | Never current |
| `label <publication_id> <text>` / `unlabel …` | Keeps a result beyond retention, or stops keeping it. | `gold.db` | No |
| `backup` | Writes and names a backup set of production. Also runs automatically. | The backups folder | No |
| `restore [<backup set>]` | Restores a set into an empty profile, catches up and records a recovery boundary ([Backup and Restore](#backup-and-restore)). | Every store | Yes, if it caught up |
| `restore --from-archive` | Last resort: rebuilds Bronze from the archive and import log, then Silver and Gold. | Every store | Yes |
| `verify` | Checks integrity. Recipe replay is pending: [#259](https://github.com/ATherkel/budget/issues/259). | `scratch/` only | No |
| `dev refresh [--inputs] [--writable]` | Development only: restores production's newest usable set ([Development](#development-diverges-from-a-stage)). | Development only | No |
| `serve` | Starts the read-only dashboard. | Nothing | No |
| `set-passphrase` | Sets the dashboard passphrase, logging out every device. | The passphrase file | No |
| `demo [--directory <new folder>] [--port <port>]` | Creates a synthetic development profile in a new folder, publishes demo accounts, sets a demo login and serves on `127.0.0.1`. Touches nothing outside the folder; refuses a folder that exists. | The new folder only | In the demo only |

A transaction's handle is the first 8 characters of its `transaction_id`.
`decide` accepts a handle and refuses one matching several transactions;
`find` lengthens a handle another Silver transaction shares, so every handle it
prints resolves.

`review` prints each quarantined run as `Run  <import run id>  <account>
<from>..<to>  <error codes>`. `--account` filters items and runs; `--kind`
lists that kind's items and no runs. A filter matching nothing prints nothing
and exits 0.

`decide`'s targets are handles, except that `void-import-run` and
`accept-discrepancy` name an `import_run_id`. Those two, `same-transaction` and
`withdrawn` rebuild from Silver; the rest from Gold. A `classify` names its
category after its handle, or takes `--adjustment`. Other fields are options:
`--counterpart <account_id>` for a `one-sided-transfer`,
`--record <payload_id>:<record_ordinal>` for a `same-transaction`, and
`--supersedes <decision_id>`, repeated per replaced decision. `decide` never
fills in `supersedes` itself.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Done. Open review items and quarantined imports are results, not failures. |
| 1 | Unexpected error: a defect. Python's own status for an unhandled exception. |
| 2 | Usage error. `argparse`'s own status. |
| 3 | Refused input: a configuration error, including a consumed account missing from `accounts.toml`; a rejected decision; a misfiled export; an import run Bronze refused; a retained payload that `rebuild --from bronze` finds declared as more than one source format or in a format this code cannot parse; an inbox file a cross-account duplicate refused; or a refused `suggest-rules --out` folder. `import` still publishes the files it stored. |
| 4 | Refused environment: no profile, a store from another profile or stage, a missing or newer migration, SQLite below the version floor, uncommitted code in production, running code other than the version a replayed recipe names (ADR-014), Silver that is unbuilt or has unknown, incompatible, or stale provenance (ADR-020), another writing command running, a store locked past its busy timeout, or `restore` into a profile that has stores. |
| 5 | Verification failed: a fingerprint mismatch, a failed integrity check, a backup set whose checksums do not match its manifest, or an import log that disagrees with Bronze. |

### Error reporting

A configuration error names the file, the entry and the problem, and `check`
lists every one before stopping:

```text
rules.toml: rule "r-mobilepay-netto": then.category "food-out" is not in taxonomy.toml
rules.toml: rule "r-furniture": when.amount_max must be a quoted decimal, got a number
decisions.jsonl: entry 7 (d-0007): targets a transaction already decided by d-0002
3 problems. Nothing was built.
```

A refused file declares nothing to check against: until `taxonomy.toml` loads,
no `then.category` is checked, and until `accounts.toml` loads, no
`when.account`. Fixing one file can reveal problems in another. A table
declared twice is invalid TOML, so the file is refused whole with the parser's
message, naming the first repeat only.

## Completeness Outputs

`status` shows, and `import`, `rebuild` and `decide` end with, the two checks
the household needs before trusting a report:

- **Balance completeness, per account:** the latest export date, *evidence
  through*, quarantined import runs, and each recent month's coverage,
  including which periods are provisional and why.
- **Classification completeness, per account and month:** unclassified money
  in, money out and count, and open review items by kind, Silver's and Gold's
  apart.

Both go to the terminal only and never change an exit code.

## Walkthroughs

All data is synthetic, from [`classification.md`](classification.md).

### W1: the monthly import

The household saves two exports to `inbox\joint-current\` and
`inbox\joint-savings\`; the folder declares the account (ADR-009).

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

Bronze needs the declared range on every export and never infers it
([`bronze-layer.md`](bronze-layer.md)). For the savings export only the
declaration says February to April were quiet rather than never exported.
Both ends are inclusive; after the first file, Enter repeats the previous
answer. Nothing is stored until the answer is `y`, and an unconfirmed import
exits 0. The summary names files by their number in the listing, never by
filename, which can carry an account number. Each stored file moves to the
archive as [`imports.jsonl`](#importsjsonl-the-import-log) describes.

`import --ranges <file>` asks nothing: the file is the declaration. It holds
`format = 1`, a `[default]` range and an `[account.<id>]` range for each
account that differs, each with TOML `from` and `through` dates. Every account
it names must be in `accounts.toml`, and an inbox account with no range and no
`[default]` refuses the whole run. Keep it outside the inputs folder and the
inbox.

Each file gets one outcome; [Failure and Retry](#failure-and-retry) says what
to do:

| Outcome | What happened |
| --- | --- |
| `stored` | In Bronze, archived and logged; the file left the inbox |
| `repeat` | The same bytes were stored for this account before; logged as a repeat |
| `stored; Silver quarantined it: <codes>` | Stored, archived and logged, but Silver holds the run back for the reasons the codes name |
| `refused` | Bronze refused the declared range, or the bytes are stored for another account |
| `misfiled` | Not imported: a filename carrying another account's number or no export date, a folder `accounts.toml` does not name, or a file in the inbox itself or in a folder inside an account's |
| `unreadable` | Not imported: another program holds the file without sharing it |
| `format failure` | Not imported: its format cannot read it, and the reason says where |
| `stored; it stays in the inbox because another program holds it` | Stored, archived and logged, but the file could not be removed |

### W2: settling a review item

```text
> budget review
unmatched-transfer  no-candidate
  3f9a2c1e  joint-current  2026-02-16  −1,000.00  TO SAVINGS
  settle with: classify, pair, one-sided-transfer, or a rule change
> budget decide classify 3f9a2c1e external-saving --reason "To Bo's savings, not imported"
Recorded d-0005.
Gold     published publication 44 (cause build)
Changes  2026-02 joint-current: expenses +1000.00 DKK; category external-saving +1000.00 DKK; group saving +1000.00 DKK; unclassified out +1000.00 DKK; unclassified count -1
Review  1 unmatched-transfer closed
```

`decide` then prints the completeness output. A rejected decision records
nothing, names every reason and exits 3.

### W3: changing a rule

Edit `rules.toml`, run `budget check`, then `budget rebuild`, and read the
printed diff. If it is wrong, `budget undo` restores the previous publication,
but fix the rules file too, or the next build brings the change back (ADR-014).

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

1. In development, `dev refresh --writable`, then `migrate`. It upgrades
   production's real history exactly as production will, legacy extraction
   and build included; its diff must show only what the migration intends.
2. In production, `migrate`: backup set, conversion, legacy extraction,
   pipeline build (ADR-014), backup set. Then `verify`.

At either step, if Silver reads as unbuilt, follow
[Provenance recovery](#provenance-recovery).

### W6: the machine dies

On the new machine, install the code version the newest set's manifest names,
write the production profile, then run `budget restore` and `budget serve`.
`restore` replays every import the live `imports.jsonl` lists beyond the set,
from the archive, and rebuilds with any decisions recorded since, so no import
or decision is lost if OneDrive had synchronised the inputs and the archive.
Gold history made after the set is lost; `restore` records a recovery boundary
so the loss reads as a gap
([Publication recovery](publications.md#publication-recovery)).

### W7: every backup set is lost

`budget restore --from-archive` rebuilds Bronze from the archive and
`imports.jsonl`, then Silver and Gold from the inputs. Reports come back
exactly; recipes, past views and legacy publications, which live only in
`gold.db`, `gold\legacy\` and their backups, are lost.

## Failure and Retry

Where a row refuses one inbox file, that file stays in the inbox, the other
files are stored and published, and `import` exits 3.

| Failure | Effect | Retry |
| --- | --- | --- |
| Configuration error, an unknown file in the inputs folder included | Nothing is built or replaced and `import` stores no file; exit 3. The same holds for refusals the files about to be imported would cause: a decision naming a dropped category, or an account closed before an incoming or Bronze transaction | Fix or remove the file and rerun |
| A declared range whose `from` falls after its `through` | At the prompt it is asked again. In a ranges file the whole file is refused, every problem listed, before anything is imported; exit 3 | Retype the range, or fix the file and rerun |
| `import` stored files, then Silver or Gold refused in a way no earlier check could foresee, or a store was busy, full or failing I/O | Bronze, the archive and the log are committed and the inbox files gone; Silver may be committed; the previous publication stays current. Production attempts its backup set and reports if that failed; exit 4 names `budget import` | Fix the cause and run `import` again, with or without inbox files: it finishes the rebuild, the publication and the backup. If the backup had failed, run `budget backup` after |
| A production `rebuild` or `undo` succeeds, then its backup set cannot be written | The stores are rebuilt or the pointer moved; exit 4, saying so | Fix what the message names, then run `budget backup` |
| `undo` with no previous publication, or with its result no longer retained | Nothing changes; exit 4 | Fix the input and rebuild |
| Refused import run (an account conflict, or a declared range that starts after it ends, ends after the export date, or leaves out the payload's first or last transaction; [`bronze-layer.md`](bronze-layer.md#rules) names each rule) | Recorded as refused and logged, its bytes copied under `exports\<account_id>\refused\` | Move the file or correct the declaration, then rerun |
| Misfiled export (filename's account number is not the declared `bank_account_number`) | Rejected before Bronze, with no run or log entry | Move it to the right folder, or fix the declaration, then rerun |
| Format failure | Found by the preview, before anything is archived or logged: `import` never presents an unreadable file to Bronze (which can still record a `FormatFailure`), so a parser fix needs no new presentation and `rebuild --from bronze` parses retained payloads again | Download the export again, or fix the parser, then rerun. Never edit an export by hand |
| A payload the inbox holds under two or more accounts (a cross-account duplicate) | Reported before anything is written, with each file's account, filename, export date, record count and dates; every file in the group is refused, with no run recorded; the others are imported only on `y` or `yes`, never without a terminal | Check which account the bank exported it from, download those accounts again, remove the duplicate, rerun |
| Crash during an import | A file whose account, original filename and payload hash already have a `stored` or `repeat` run no decision voids is finished (archived, logged once, removed) without a new run; any other unlogged run is logged by the next import | Rerun `import` |
| The archive or the import log disagrees with Bronze: no free place for a run's bytes, a damaged or extra log line, an entry for a run Bronze lacks, or a cut-off last entry | As [`imports.jsonl`](#importsjsonl-the-import-log) says: nothing is overwritten, and the import stops before writing or completes the entry, naming what to fix | Move the conflicting file aside, restore the log from the newest set, or restore Bronze up to the log, as named |
| A logged run's archived copy is saved over, and its file is presented again | Nothing is overwritten; the file stays in the inbox; other imports go on | Put the run's export back where its entry says, then rerun |
| An inbox file is saved over or removed during its import | The bytes that were read are stored, archived and logged; a new file stays in the inbox | Rerun `import` if a file remains |
| An inbox file is held open by another program | Imported, but the file stays in the inbox | Close the program and rerun; the file is removed as a retry |
| An inbox file is held without sharing, so it cannot be read | Not imported | Close the program, then rerun |
| Crash during a build | SQLite rolls back; the previous publication stays current | Rerun the command |
| Another writing command is running | Exit 4 at once; nothing written | Rerun when it ends. On Windows a killed command's lock is released a moment late, so an immediate rerun can be refused once |
| A decision-log line cut off by a crash | `check` reports it; `decide` refuses | Delete the partial last line |
| Crash while writing a backup set | The set stays in `backup-staging\` or as `.partial`, is never used, and the next backup deletes it | Nothing to do |
| The backup before a migration cannot be written or verified | The migration does not begin; exit 4, or 5 when a copy or the import log does not verify | Fix what the message names, then rerun `migrate` |
| A migration fails | No step of it commits and the store keeps its version, though an earlier stage that migrated (Bronze before Silver, both before Gold) keeps its new one; the first set stays held for recovery | Fix the defect; the held set restores the stores if needed |
| A Silver migration clears a pre-provenance result, or Gold sees missing, unknown, incompatible or stale provenance | Silver may read as unbuilt; Gold refuses before publishing and reports the state | Follow [Provenance recovery](#provenance-recovery) |
| The backup after a migration fails | The store is migrated; the first set stays held; exit 4 | Fix what the message names, then run `budget backup` |
| `migrate` finds no production store for a stage, or only an empty file an interrupted start left | Nothing changes in any stage; exit 4. Likewise `--new-store` when a store it would start already exists (naming the `--stage` that starts the rest), and Silver or Gold when Bronze has no store, since every set holds Bronze | Move every store out and run `budget restore`; or, for a first store, rerun with `--new-store`, adding `--stage` when another stage's store exists |
| A store a complete backup set holds is missing, or only an empty file an interrupted start left | `backup`, and a `migrate` that would back up, change nothing; exit 4 | Move every store out, then run `budget restore`: a store is never restored beside live ones |
| OneDrive offline | Complete backup sets wait in the local OneDrive folder | Nothing to do |

A genuine repeat export has a new export date in its filename, so it reaches
Bronze as a new `repeat` run.

## Backup and Restore

- **A backup set** is a folder `backups\<UTC time>\`, named to the microsecond
  with `-` for `:`, such as `2026-05-02T18-05-11.120731Z`. It holds a
  backup-API snapshot of every store, a copy of the inputs folder under
  `inputs\`, and `manifest.json`. The export archive is not copied, because
  Bronze holds each payload's bytes.
- **It covers every store the profile has**: `bronze.db` and, once they exist,
  `silver.db` and `gold.db`. A backup is refused while the stores folder holds
  another store, such as `gold\` legacy extracts or any other SQLite file, and
  once a complete set holds a Silver or Gold store, while that store is
  missing: either set would misstate the profile. An older set holding only
  earlier stages stays complete, and never stops `migrate --new-store`.
- **The manifest** records, in this order:

  ```json
  {
    "format": 1,
    "profile": "production",
    "created_at": "2026-05-02T18:05:11.120731+00:00",
    "code_version": {"package": "0.1.0", "source_sha256": "9f2c…"},
    "stores": {
      "bronze": {"path": "bronze.db", "schema_version": 1},
      "silver": {"path": "silver.db", "schema_version": 1},
      "gold": {"path": "gold.db", "schema_version": 1}
    },
    "logs": {"imports.jsonl": 1730, "decisions.jsonl": 0},
    "files": {
      "bronze.db": {"sha256": "c0ffee…", "bytes": 81920},
      "silver.db": {"sha256": "beefed…", "bytes": 90112},
      "gold.db": {"sha256": "facade…", "bytes": 131072},
      "inputs/accounts.toml": {"sha256": "5ca1ab…", "bytes": 412},
      "inputs/imports.jsonl": {"sha256": "0ddba1…", "bytes": 1730}
    }
  }
  ```

  `logs` gives each log's length in bytes over complete lines only; a missing
  log has length 0. `code_version` is the package version and a SHA-256 of its
  source: one line per `.py` and `.sql` file in the installed `budget` package,
  sorted, each its `/`-separated path, a tab, its SHA-256 and a line feed, so
  any checkout can be compared with or without git.
- **The snapshot and the import log agree**, as an import checks before it
  writes: a blank, damaged or second entry, or one for a run the snapshot
  lacks, refuses the set with exit 5. Unlogged runs and a cut-off final line
  are backed up as they are.
- **When**, in production only:
  - `migrate`: one set before it changes an existing store and one after the
    last change (stores change in the order Bronze, Silver, Gold), a new store
    included; none when nothing changed.
  - `import`, after presenting a file to Bronze, once Silver is rebuilt and
    Gold published or held back. An empty inbox writes one only when it
    finished earlier work; an unconfirmed import writes none. What would refuse
    the set refuses the import before its first Bronze write; a set that still
    fails leaves the imports committed, exits 4 and says to run `budget backup`.
  - `rebuild` that wrote stores, and `undo` that moved the pointer.
  - `decide` that recorded a decision, even when its rebuild refuses, because
    nothing else rebuilds the log. A set that then fails is named after the
    refusal, and `decide` still exits 3 and says to run `budget backup`.
  - `budget backup`.
- **Written whole or not at all.** A set is staged in the profile's local
  `backup-staging\`, `manifest.json` last, copied to the backups folder as
  `<name>.partial`, checked against the manifest, then renamed. It never
  replaces another set. A set without a manifest, or with mismatched checksums,
  is incomplete and never selected; `restore` and `dev refresh` skip it
  silently. A failure removes what it staged, and the next backup deletes what
  a crash left in staging or as `.partial`, never a folder under a set's own
  name.
- **Kept**, by the production profile's `[backups]` keys: every set from the
  last `keep_all_days` (14), then the newest of each day for `keep_daily_days`
  (365), then the newest of each month for `keep_monthly` months, counting the
  current one, or for good with `"forever"`, the default. Days and months are
  UTC. Each backup prunes after it is published and keeps itself. Retention
  reads only manifests, deletes a set by renaming it to `<name>.partial` first,
  and leaves a failed deletion to the next backup. Every set is a full copy,
  so a year of daily sets can take gigabytes.
- **Never pruned:** a set whose manifest format this code cannot read, and a
  set held for recovery. `migrate` holds its first set in
  `recovery-sets.json` and releases it once a migration succeeds and its own
  set is written. A later backup also releases a held set once any store it
  records is at an older schema version than the new set's. While that file
  cannot be read, nothing is pruned.
- **Where:** OneDrive, which is safe for closed files, unlike a live database
  with its WAL files (ADR-013).
- **`restore`** writes only into a profile with no stores; to recover a damaged
  one, first move its `.db` files and `gold\legacy\` out. It takes the newest
  complete set this code can use, or the one named, checks every SHA-256,
  runs `PRAGMA integrity_check`, and migrates older stores. It names each newer
  complete set it passes over as unreadable or damaged; with none usable it
  restores nothing and names them all. It restores every store in the set
  together. It then catches up from the live inputs, or the set's copy of any
  missing one, replays the import log [by its rules](#importsjsonl-the-import-log)
  from the archive, and publishes if the recipe changed. A surviving decision
  log must extend the set's copy, or `restore` stops. Publications after the
  set are lost ([Publication recovery](publications.md#publication-recovery)).
- **`dev refresh`** refuses if any complete set is another profile's, then
  picks a set and names those it passes over as `restore` does.
- **`verify`** runs `PRAGMA integrity_check` on every store and checks that the
  import log agrees with Bronze and that the decision-log prefix hashes match.
  Recipe replay is pending
  ([`publications.md`, *Verify*](publications.md#verify)).

## Dashboard Access

- `serve` binds to the profile's address and port: the home network address in
  production, `127.0.0.1` in development, which is also the `bind` default;
  `port` defaults to 8750. A Windows firewall rule allows the port on private
  networks only, and nothing is reachable from the internet. Reserve the
  production address for the PC in the router, or `serve` fails when it
  changes.
- One household passphrase guards every page, stored as a `scrypt` hash in the
  absolute path `[dashboard] passphrase_file` names: under `%APPDATA%\budget\`
  in production, never in OneDrive or the repository. `set-passphrase` asks
  twice, refuses an empty or mismatched one, and replaces the file whole.
  `serve` refuses to start without one, and rereads the file on every login and
  cookie check, so a change applies without a restart.
- A login sets an `HttpOnly`, `SameSite=Strict` session cookie holding its
  expiry, signed with a key derived from the passphrase hash. There is no
  session store, so restarting `serve` keeps logins.
- A login lasts while it is used: every request renews the cookie for 30 days,
  which is also its `Max-Age`, with no cap on total age.
- After 5 failed logins in a row, every login is refused (HTTP 429) for 30
  seconds, each further lock twice as long, up to 15 minutes; 5 more failures
  after a lock lock again, and a success resets the count. One count serves the
  household.
- These limits and the 30 days are code constants, not profile settings.
- Logout deletes the cookie in that browser only. `set-passphrase` logs out
  every device, for a lost device or a leaked cookie.
- **Plain HTTP on the home network is an accepted risk**: someone on the same
  Wi-Fi could read the passphrase and pages. HTTPS with a locally trusted
  certificate is the upgrade path, and adds the cookie's `Secure` flag.
- The dashboard opens only `gold.db`, read-only, through analytics. It has no
  writing route except login and logout, and no response may be cached.
- It runs while `budget serve` runs; a Task Scheduler entry can start it with
  Windows.

### Away from home

The household's own devices reach the dashboard over a private
[Tailscale](https://tailscale.com) network, a tailnet. Tailscale gives the PC
an HTTPS address that only devices signed in to the tailnet can open; the
passphrase still guards every page.

1. Install Tailscale on the PC and on each phone, and sign in on all of them
   with the household's Tailscale account.
2. Run `budget serve`, then `tailscale serve 8750`. Tailscale prints the
   address, such as `https://<pc>.<tailnet>.ts.net`.
3. Open that address on the phone and log in.

Tailscale forwards to the port on `127.0.0.1`, the default `bind`. A profile
that binds another address or port gives Tailscale the same:
`tailscale serve http://<bind>:<port>`. To try it first, run `budget demo` and
`tailscale serve 8765`, the demo's port.

- **Never** port-forward the dashboard, tunnel it through a service such as
  ngrok, or use `tailscale funnel`: each one puts it on the public internet.
- Only the household's own devices join the tailnet.
- Tailscale's coordination server, run in the US, learns which devices are in
  the tailnet but not the dashboard's traffic, which is encrypted between the
  devices. The household accepts that. Headscale, a self-hosted coordination
  server, is the alternative if it stops being acceptable.

## Logging

Routine logs are JSON Lines under the profile's `logs\` folder, rotated by
size.

- **Allowed:** the command, profile, event, counts, durations, schema and code
  versions, error codes, and the identifiers `import_run_id`,
  `publication_id`, `decision_id`, and review item kinds.
- **Never:** amounts, balances, descriptions, bank category labels, original
  filenames, or `transaction_id`s, which hash transaction content.
- **Never an OS error's text:** a failure event carries only the exception
  class name and `import_run_id` where known, never an `OSError`'s
  `str(error)`, `filename` or `filename2`, which carry paths. The terminal may
  show it.

A test runs every walkthrough on synthetic data and asserts that no fixture
amount, description or filename reaches the log.

## Proved Outside Production First

A procedure runs in production only after it passed in the test profile and
ran at least once in development against a restored production backup.

| Procedure | Test profile, every CI run | Development |
| --- | --- | --- |
| `migrate` | Every migration from empty, and from the previous release's fixture stores | Rehearsed after `dev refresh --writable`, before production |
| Import and its retry | Idempotent rerun, and a crash injected after each step | Real exports' shapes, through `upstream` |
| Publishing | Crash before and after the commit point; `undo`; retention deletion | Every `rebuild` publishes |
| Legacy publications | A Gold migration that cannot convert a labeled result: extract, legacy entry, and a backup set retention keeps | With the migration's rehearsal |
| Backup and restore | Backup, restore into an empty profile, `verify`; a set cut off before its manifest is skipped; `restore` replays imports logged after the set | Every `dev refresh` is a restore |
| `restore --from-archive` | Rebuilds the fixtures' reports exactly | Once before it is first trusted, then yearly |
| Log redaction | Asserted on every walkthrough | — |
| Profile guards | Every refusal: no profile, wrong profile, a production store outside `upstream/`, a test path outside the temporary directory, a second writing command | — |
| Decision log | A hand-added line that breaks a rule; an edited prefix; a cut-off last line | — |

## Cutting a Release

A store records only the number of its last migration (`PRAGMA user_version`),
so a migration file a release shipped is frozen. Migrations added since the
last release tag stay editable.

Before tagging a release:

1. Merge each store's unreleased migrations into one file for that store, a
   file merge, not a git squash: unreleased `gold/0001` to `gold/0005` become
   one `gold/0001_create_gold_store.sql`. Each schema moves at most one number
   per release.
2. If the release adds migration files, add a table for the new tag to
   `src/budget/migrations/released.toml`, mapping each new file to its SHA-256
   after converting CRLF to LF. A table lists only files no earlier table
   lists. `tests/test_released_migrations.py` fails when a listed file changes
   or disappears; it reads only the manifest and working tree, because CI
   checks out without tags.
3. Bump the version with
   [`uv version --bump <major|minor|patch>`](https://docs.astral.sh/uv/guides/package/#updating-your-version).
   The Release workflow tags that version and refuses one whose tag exists,
   unless the tag has no GitHub release, points at this commit, and
   `adopt_existing_tag` is ticked.
4. Run the Release workflow from `main`. Its check (`pytest -m release` with
   `RELEASE_TAG` set to `v` plus the version) refuses a migration file in no
   table, or a changed released migration, and its summary lists the lines to
   paste into `released.toml` or the files to restore. A run from another
   branch, or with `dry_run`, is a rehearsal that creates no tag.

To run the check locally in PowerShell, clear the variable afterwards, or later
`uv run pytest` runs include it:
`$env:RELEASE_TAG = "v$(uv version --short)"; uv run --locked pytest -m release; Remove-Item Env:RELEASE_TAG`.

`migrate` refuses a store whose schema is newer than the code (exit 4). A
development store that ran migrations later merged away is reset, not
upgraded: delete development's stores, run `budget migrate` (outside
production it starts missing stores without `--new-store`), then
`budget dev refresh` for real data. Production is prerelease, so a merge needs
no upgrade path for it.

## Tooling

- `uv` with a uv-managed Python 3.12 or newer, whose SQLite meets ADR-013's
  floor, on the household machine and in CI.
- The pipeline commands use only the standard library: `argparse`, `tomllib`,
  `json`, `sqlite3`, `hashlib`, `logging`. The dashboard (`serve`,
  `set-passphrase`) adds FastAPI with uvicorn, Jinja and htmx, whose script
  ships in the package so nothing is fetched from the internet.
- `git` on the household machine, so a production build can name its commit
  and refuse uncommitted code (ADR-014).
- The quality gate: ruff, ty, complexipy, pytest.
