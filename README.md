# Budget

A Python-first, self-hostable household budget platform. It is designed around
an immutable Bronze → Silver → Gold data pipeline so reports remain independent
of bank and import format.

Start with the [documentation map](docs/README.md) and the
[delivery roadmap](docs/03-roadmap.md).

## Privacy and terms

The [privacy scaffold](PRIVACY.md) and [terms scaffold](TERMS.md) contain sourced
headings and blanks for the owner to complete. They are not finished policies
and must not be used as registration documents yet. The originals and their
reuse conditions are linked in the files and in the
[template research](docs/research/minimal-privacy-and-terms.md).

After the owner completes and reviews both documents and they are merged into this
public repository's `main` branch, the URLs for that installation's Enable
Banking registration are:

- Privacy: <https://github.com/ATherkel/budget/blob/main/PRIVACY.md>
- Terms: <https://github.com/ATherkel/budget/blob/main/TERMS.md>

Until then, use the rendered files on the PR branch for review. Another
operator must complete the documents for their own
identity, contact email, deployment, and data handling, publish their own URLs,
and register their own Enable Banking application with their own credentials.
The provider's personal-use conditions still apply to each installation.

## Install and test

`uv` manages the environment, the standard library's `unittest` runs the tests,
and the quality gate is ruff, ty and complexipy. The runtime has no third-party
dependencies, so there is nothing else to install.

```powershell
uv sync
uv run python -m unittest discover -v -s tests -p 'test_*.py' -t .
```

`uv sync` creates `.venv/`, installs the `budget` distribution from `src/budget`
in editable mode, and is the whole setup step. `uv build` writes a wheel and an
sdist into the ignored `dist/` directory; installing that wheel is what proves
the package works outside the checkout, so nothing relies on `PYTHONPATH` or a
hand-edited `sys.path`. Python 3.12 or newer is required.

Every Python change must pass the repository's quality gate before it is
committed, and CI runs the same four checks:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run complexipy
```

[docs/agents/code-quality.md](docs/agents/code-quality.md) says what each check
enforces and why a complexity failure is a design signal rather than a
threshold to raise.

In VS Code, select `.venv/Scripts/python.exe` with **Python: Select
Interpreter** if the workspace was already using system Python.
`python.defaultInterpreterPath` only supplies the default for a window that has
no interpreter selected yet, so it does not replace a selection you already
made.

## Layout

| Path | Contents |
| --- | --- |
| `src/budget/` | the application package |
| `src/budget/cli.py` | the `budget` command line |
| `src/budget/bronze/` | Bronze: raw payloads, import runs, source records |
| `src/budget/bronze/parsers/` | the parser contract, the registry, and one module per source format |
| `tests/` | `unittest` suites, discovered from the repository root |
| `docs/` | contracts, decisions, and domain documents |

## Adding a source format

Parsing is separated by source, representation, and version:
[docs/developers/source-parsers.md](docs/developers/source-parsers.md) describes
the contract, how to register a format, and what is deliberately not solved yet.

## Storage and profiles

A profile is an immutable value that names the folder its stage stores live in,
the inputs folder the household authors, the inbox exports wait in, and the
export archive. Nothing is selected implicitly, and a test profile refuses any
path outside the temporary directory it was built from:

```python
import os
from datetime import date
from pathlib import Path

from budget.bronze import BronzeStore, ImportDeclaration, migrate_bronze
from budget.profiles import Profile

local = Path(os.environ["LOCALAPPDATA"]) / "budget"
profile = Profile(
    name="development",
    stores=local / "dev",
    inputs=local / "dev-household" / "inputs",
    inbox=local / "dev-household" / "inbox",
    exports=local / "dev-household" / "exports",
)
source = local / "dev-household" / "inbox" / "daily-account" / "danske-20260914.csv"
migrate_bronze(profile)

with BronzeStore(profile) as store:
    run = store.import_file(
        source,
        ImportDeclaration(
            declared_account_id="daily-account",
            source_format="danske-csv-v1",
            covers_from=date(2026, 6, 14),
            covers_through=date(2026, 9, 13),
        ),
    )
```

A store holds real bank data, so keep it outside the checkout, where
`git add` could pick it up, and outside a synchronised folder such as OneDrive,
where a live SQLite file can be corrupted (ADR-013). The example follows
[operations.md](docs/architecture/operations.md), which puts every profile's
stores under `%LOCALAPPDATA%\budget\`.

A profile name is one of `development`, `production` or `test`; a test profile
must name the temporary root it stays inside, and every path it derives,
including the store file itself, is resolved and re-checked against that root on
each access, so a folder or file replaced by a symlink is refused instead of
followed. The command line below builds a development or production profile
from a profile file; a test profile is never a file.

`migrate_bronze` and `migrate_silver` are the only operations that create or
upgrade a store. Both run one shared runner, `budget.sqlstore`, over their own
numbered SQL files, `migrations/bronze/` and `migrations/silver/`, which ship
inside the installed wheel and sdist so an installation can migrate without a
source checkout. Each store records its own `PRAGMA user_version` and a one-row
`store_identity` naming the profile and stage. The runner applies every
pending file in one transaction, so a migration that fails leaves the store at
the version it had. Gold's store will run the same runner over
`migrations/gold/`. Opening a store never creates or changes the schema: it
requires an existing file, `mode=rw`, a version this code knows, and a
matching identity, and it sets `foreign_keys = ON`, `busy_timeout = 5000` and
`synchronous = FULL`. A new store is created in WAL mode.

## Silver persistence

`silver.db` holds the output of one Silver build, so the pipeline does not have
to rebuild it to read it. `SilverStore` is the seam: `replace(result,
currencies=...)` writes one complete `SilverResult` in one transaction, and
`read()` returns the complete result with `Decimal` money and the order the
build produced. A read spans several tables, so it takes one SQLite snapshot;
a failed replacement rolls back and leaves the previous result readable.

```python
from budget.silver import SilverStore, migrate_silver, rebuild_silver

migrate_silver(profile)

with SilverStore(profile) as store:
    result = store.read()
```

Amounts and balances cross this boundary as `Decimal` and are stored as
`INTEGER` counts of the currency's minor unit (ADR-013). The conversion is
exact integer arithmetic: an amount with more decimal places than its currency
allows, a non-finite value, one outside SQLite's 64-bit integer range, or one
in a currency the ISO 4217 table does not know is refused before anything is
written. The result's account currencies are stored with it, so unbooked
amounts and balance observations decode without re-reading mutable
configuration.

`rebuild_silver(profile, inputs=SilverBuildInputs(...))` is the entry point a
pipeline command calls: it holds the profile's writer lock, runs the pure
`budget.silver.build` over the inputs, replaces the stored result with what the
build produced, and returns it. The inputs are one frozen value object
(`runs`, `source_records`, `format_failures`, `currencies`, `decisions`) rather
than a long argument list, and `build`'s own signature is unchanged. A command
that already holds the profile's writer lock passes that `WriterLock` in place
of the `Profile`, so one command keeps one lock instead of acquiring a second.

`budget rebuild --from silver` is that command. It holds the profile's writer
lock for its whole run — the guard, the Bronze read, the replacement, the
summary and the routine log — so a competing command exits 4 at once. Only
`silver` is built so far: `--from bronze` and `--from gold` refuse with exit 4,
and Gold publishing, `dev refresh` and restore are later slices. A rebuild always reads the profile's own local stores, so production
data reaches development only through a restored backup set, which is not built
yet.

When `inputs/decisions.jsonl` holds any decision, the rebuild refuses with exit
3 and says so: the decision-log reader is a later slice, and a build must not
silently ignore a household decision. A missing log, or one holding only a
byte-order mark and whitespace, means no decisions and is allowed.

`budget review [--kind <kind>] [--account <id>]` lists the open Silver review
items, then each quarantined import run that no open item already shows. An item
line names the review item, its kind, its account, its date range, the import
run and payload identifiers it came from, and, for a dropped transaction, the
first eight characters of its `transaction_id` as the handle. A run line reads
`Run  <import run id>  <account>  <from>..<to>  <error codes>`, for a run such
as one quarantined by validation errors alone. A run quarantined by a balance
break appears once, through its review item, and an accepted run never appears.
`--account` filters both kinds of line; `--kind` names an item kind, so it lists
that kind's items and no runs. A filter that matches nothing exits 0 and prints
nothing. Review only reads the persisted Silver result: it takes no writer lock
and needs neither a Bronze store nor `accounts.toml`.

`migrate_bronze` refuses the production profile: production is migrated only
by `budget migrate`, which backs the store up first (see below).
`BronzeStore(profile, parsers=...)` accepts an optional mapping for
tests that need two versions of one format; the mapping is copied, and a parser
registered under an ID it does not name is refused.

## Importing the inbox: `budget import`

Save each export in its account's inbox folder, `inbox\<account_id>\`: the
folder is the account declaration. Then run `budget import`. For each file it
shows the account, the filename, the export date the name carries, and the
file's first and last transaction dates, and asks for the range you asked the
bank for. Both ends are inclusive. After the first file, Enter gives the same
answer as the file before. Nothing is stored until you answer `y`.

This run is on a synthetic development profile. Its inbox holds an export
for each account, and a second `joint-current` export whose filename carries
another account's number:

```text
> budget import
[1] joint-current  Joint-0012345678-20260331.csv
    exported on    2026-03-31 (from filename)
    transactions   2026-03-02..2026-03-28, 2 source records
    Enter the range you asked the bank for.
    from: 2026-03-01
    through: 2026-03-31
[2] joint-current  Konto-0099999999-20260331.csv
    misfiled: account "joint-current": the export's filename carries another bank account number than accounts.toml declares; move the file to its account's inbox folder, or correct the declaration; it stays in the inbox
[3] joint-savings  danske-20260331.csv
    exported on    2026-03-31 (from filename)
    transactions   2026-03-31..2026-03-31, 1 source record
    Enter the range you asked the bank for.
    from [2026-03-01]:
    through [2026-03-31]: 2026-03-30
Import 2 files? [y/N] y
[1] joint-current  stored
[2] joint-current  misfiled: account "joint-current": the export's filename carries another bank account number than accounts.toml declares; move the file to its account's inbox folder, or correct the declaration; it stays in the inbox
[3] joint-savings  refused: the file has transactions after the declared range ends; it stays in the inbox
Silver   1 admitted, 0 quarantined, 0 dropped
```

The exit status is 3, because two files stayed in the inbox. Each file is
imported on its own: `joint-current`'s export was stored, archived under
`exports\joint-current\`, logged in `inputs\imports.jsonl`, and removed from
the inbox, whatever happened to the others. Then Silver was rebuilt from
everything Bronze holds. In production a backup set of both stores follows,
and the summary ends `Backup   backup set <name> written`.

The summary names a file by its number in the listing, never by its
filename, because a bank's filename can carry an account number. The routine
log records counts only.

| Outcome | What happened | What to do |
| --- | --- | --- |
| `stored` | In Bronze, archived and logged; the file left the inbox | Nothing |
| `repeat` | The same bytes were stored for this account before; logged as a repeat | Nothing |
| `stored; Silver quarantined it: <codes>` | Stored, archived and logged, but Silver holds it back; the codes say why, as `budget rebuild --from silver` does | Read the codes; a reader or mapping fix and a rebuild settle it |
| `refused` | Bronze refused the declared range, or the bytes are already stored for another account; a copy is kept under `exports\<account_id>\refused\` | Correct the range, or move the file, then rerun |
| `misfiled` | Not imported: a filename carrying another account's number or no export date, a folder `accounts.toml` does not name, or a file in the inbox itself or in a folder inside an account's | Move or rename the file, or correct `accounts.toml`, then rerun |
| `unreadable` | Not imported: another program holds the file without sharing it | Close that program, then rerun |
| `format failure` | Not imported: its format cannot read it; the reason says where | Download the export again without opening it, or wait for a reader fix, then rerun. Never edit the file: the archive keeps the bank's exact bytes |
| `stored; it stays in the inbox because another program holds it` | Stored, archived and logged, but the file could not be removed | Close that program, then rerun: the rerun removes it and adds no run |

| Exit | `import` |
| --- | --- |
| 0 | Every file was stored or a repeat; or the inbox is empty; or you did not answer `y` |
| 3 | A file was refused, misfiled, unreadable or a format failure, and stays in the inbox. Also, with nothing stored: a ranges file or `accounts.toml` that breaks its rules, a decision log holding a decision (its reader is not built yet), or an account Silver cannot build |
| 4 | Nothing stored: another command is running, or production's code is uncommitted, or its stores folder holds a store no backup set covers. After the imports: production's backup set could not be written; run `budget backup` once the message's problem is put right |
| 5 | Nothing stored: `imports.jsonl` disagrees with Bronze |

The range is the one you set on the bank's slider. It is never inferred from
the filename, the file or the export date: only the declaration says that a
quiet month was quiet rather than never exported
([`bronze-layer.md`](docs/architecture/bronze-layer.md)).

### The ranges file

`budget import --ranges <file>` reads the ranges from a file you write
instead of asking, and does not ask you to confirm: the file is the
declaration. It holds a default range and a range for each account that
differs, because one inbox can hold exports downloaded on different days:

```toml
format = 1

[default]
from = 2026-03-01
through = 2026-03-31

[account.joint-savings]
from = 2026-01-01
through = 2026-03-30
```

Dates are TOML dates, without quotes. Every `[account.<id>]` must name an
account in `accounts.toml`, so a misspelt one is refused rather than
silently given the default. An account with a file in the inbox and no range
of its own, when there is no `[default]`, refuses the whole run. A file that
breaks a rule lists every problem and imports nothing, with exit 3. Keep it
outside `inputs\`, which holds only the household's input files, and
outside the inbox.

### A rerun

Rerunning `budget import` is always safe. A file whose account, filename and
bytes already have a stored or repeat run is finished, not imported again:
archived and logged once, and removed from the inbox. A refused file is
presented again, with whatever range you now declare. An import interrupted
after its files left the inbox but before Silver was rebuilt leaves nothing
in the inbox to rerun: run `budget rebuild --from silver`, and in production
`budget backup`.

`budget.importing.import_inbox_file` is the Bronze step `import` runs for each
file, under its one writer lock;
[operations.md](docs/architecture/operations.md#importsjsonl-the-import-log)
gives its rules.

## Silver walkthrough

`examples/silver_walkthrough.py` runs the whole story on synthetic data in one
temporary folder, with no input from you. It writes a development profile and
a `joint-current` account, saves a March export in `inbox\joint-current\`,
runs `budget import` and `budget review`, then does the same with an April
export whose balance chain breaks. The profile, inbox, ranges files, stores,
archive, import log and routine log all stay in that folder, and nothing
outside it is read or written. Run it with:

```powershell
uv run python examples/silver_walkthrough.py
```

Each import declares its range in a ranges file
([see above](#the-ranges-file)) beside the profile, so nothing asks at the
prompt. March's `ranges-march.toml` is:

```toml
format = 1

[default]
from = 2026-03-01
through = 2026-03-05
```

Each command line ends with its exit status after `->`, and the lines indented
under it are what the command printed. A line starting with `#` is the
script's own note, not command output. Every identifier the commands print is
real. The script replaces each run of 16 or more lowercase hexadecimal
characters with `<id>`, so this transcript is reproducible:

```text
budget migrate -> 0
budget import --ranges ranges-march.toml -> 0
  [1] joint-current  stored
  Silver   1 admitted, 0 quarantined, 0 dropped
budget review -> 0
# (no output: no open review items)
budget import --ranges ranges-april.toml -> 0
  [1] joint-current  stored; Silver quarantined it: balance-break, balance-chain-break
  Silver   1 admitted, 1 quarantined, 0 dropped
budget review -> 0
  <id>  balance-break  joint-current  2026-04-02..2026-04-02  run <id>  payload <id>
```

Each import rebuilds Silver from everything Bronze holds, so the walkthrough
runs no `budget rebuild --from silver` of its own. The profile is a
development one, so no backup set follows; in production the summary would
end `Backup   backup set <name> written`. The April import exits 0 even though
Silver quarantines its run: a quarantine is a result, not a failure, and the
file was stored, archived and removed from the inbox. `budget review` prints
nothing when no item is open, and exits 0.

## Command line

`uv sync` installs a `budget` command; `python -m budget` runs the same thing.
Every command needs a profile file, named by `--profile` or, failing that, the
`BUDGET_PROFILE` environment variable. There is no default profile. Keep
profile files outside the repository, for example in `%APPDATA%\budget\`. This
PowerShell writes a development profile there, and refuses to replace one that
already exists:

```powershell
$local = "$env:LOCALAPPDATA\budget"
New-Item -ItemType Directory -Force "$env:APPDATA\budget" | Out-Null
@"
format = 1
profile = "development"

[paths]
stores = '$local\dev'
inputs = '$local\dev-household\inputs'
inbox = '$local\dev-household\inbox'
exports = '$local\dev-household\exports'
"@ | Out-File -NoClobber -Encoding utf8 "$env:APPDATA\budget\development.toml"
```

PowerShell fills in `$env:LOCALAPPDATA` as it writes, so the file holds absolute
paths such as `C:\Users\<you>\AppData\Local\budget\dev`: the application never
expands variables in a profile file.

The file is UTF-8 text, with or without a byte-order mark, and may hold only
the keys
[operations.md](docs/architecture/operations.md#selecting-a-profile)
documents for its profile: `[backups]` and `paths.backups` belong to
production, and `paths.upstream_backups` to development. `[paths].stores`,
`[paths].inputs`, `[paths].inbox` and `[paths].exports` are required and must
be absolute, and the inbox and exports folders may not overlap. `profile` is
`development` or `production`.

```powershell
budget --profile "$env:APPDATA\budget\development.toml" migrate
```

`migrate` creates or upgrades the profile's Bronze and Silver stores, Bronze
first, and `--stage bronze` or `--stage silver` names one of them. Every stage
goes through the same runner, so each one refuses the same way: a store
recorded for another profile or another stage, or at a schema version this
code does not know, is left as it is and refused with exit 4. `--stage gold`
is refused with exit 4 until that store exists. A run that succeeds prints
nothing:

```powershell
$env:BUDGET_PROFILE = "$env:APPDATA\budget\development.toml"
budget migrate --stage bronze; $LASTEXITCODE   # 0: bronze.db created or upgraded
budget migrate --stage silver; $LASTEXITCODE   # 0: silver.db created or upgraded
budget migrate; $LASTEXITCODE                  # 0: both, already current
budget migrate --stage gold; $LASTEXITCODE     # 4
# budget: the gold stage is not built yet: only bronze and silver can be migrated
```

Had `bronze.db` been replaced by a copy of `silver.db`, `migrate` would refuse
it rather than adopt it:

```text
budget: C:\Users\<you>\AppData\Local\budget\dev\bronze.db cannot be opened: it belongs to profile 'development' stage 'silver'
```

A writing command holds the operating system's lock on `budget.lock`
in the stores folder for its whole run, so a second one refuses at once. On
Windows the lock of a command that was killed or crashed is released a moment
late, so an immediate rerun can report another command running; rerun it
shortly.

A production profile file also names `[paths].backups`, the folder backup sets
are published in, and may hold a `[backups]` table of retention keys
(`keep_all_days`, `keep_daily_days`, `keep_monthly`); the backups folder may
not overlap the stores, inputs, inbox or exports folders. In production,
`migrate` writes a verified backup set before it changes an existing store
and another after, and a migration that fails commits none of its steps. A
set holds the Bronze store and the Silver store, each snapshotted through
SQLite's backup API, so production migrates both stages as development does.
A missing production store is started only with `--new-store`, only where
none of the stores it would start is started already, Silver's only beside a
Bronze store a set can hold, and only when no complete backup set holds one
that could restore it instead. A store file left empty by an interrupted
start counts as missing: rerunning `--new-store` starts it, or, where an
earlier stage's store was started, names the `--stage` that starts the rest.
`budget backup` writes a set of production by hand and prints its name.
`budget import` writes a set after its Bronze writes and the Silver
rebuild that follows them.
[operations.md](docs/architecture/operations.md#backup-and-restore) describes
the sets, their manifest and retention.

A new production profile starts both stores in one run, then writes its
first set:

```powershell
$env:BUDGET_PROFILE = "$env:APPDATA\budget\production.toml"
budget migrate --new-store; $LASTEXITCODE   # 0: bronze.db and silver.db created, then a backup set
budget migrate; $LASTEXITCODE               # 0: both already current, so no new set
budget backup; $LASTEXITCODE                # 0
# backup set 2026-10-06T15-28-41.154905Z written
budget migrate --new-store; $LASTEXITCODE   # 4
# budget: C:\Users\<you>\AppData\Local\budget\production\bronze.db is already a Bronze store: migrate it without --new-store
```

A production profile whose Bronze store and sets come from before sets held
Silver has no Silver store yet. `migrate` refuses, before Bronze changes,
until Silver's is started. Its older sets hold Bronze alone; they stay
complete and are kept like any other set, and since they hold no Silver
store, they do not stop one being started:

```powershell
budget migrate; $LASTEXITCODE                              # 4
# budget: the production profile has no Silver store: start one with `budget migrate --stage silver --new-store`, unless production had one, which must be restored from a backup set instead
budget migrate --stage silver --new-store; $LASTEXITCODE   # 0: silver.db created, then a set of both stores
```

Once a complete set holds a Silver store, a lost one must be restored, not
started anew, and no backup is written until it is; a file an interrupted
start left empty in its place counts as lost. Before then, a backup leaves
such a file out. A backup is still refused
while the stores folder holds a store no set covers, such as Gold's, since
the set would not be a complete copy of the profile. All three exit 4 and
write nothing:

```text
budget: the backups folder holds complete backup sets of this profile, so its Silver store must be restored from the newest that holds one, not started anew; nothing was written
budget: the stores folder has no Silver store, but backup sets of this profile hold one: the Silver store must be restored from the newest that holds one; nothing was published
budget: the stores folder holds gold.db, which no backup set covers yet: only the Bronze and Silver stores are backed up; nothing was published
```

| Exit | Meaning |
| --- | --- |
| 0 | Done |
| 1 | Unexpected error: a defect, such as a broken packaged migration |
| 2 | Usage error, including a command that is not built yet |
| 3 | The profile file is missing, unreadable, not UTF-8, invalid or of an unknown format; an input file or a ranges file breaks its rules; or `import` left a refused, misfiled, unreadable or unparsable file in the inbox |
| 4 | Refused environment: no profile, a production store missing or asked for anew where one or its backup sets exist, a stage not built yet, a store of another profile, stage or schema version, SQLite below the floor, a stores folder that cannot be used, a store another program holds, another command running, a backup set that cannot be written, a store no backup set covers yet or one its backup sets hold gone missing, or a store migrated, or exports imported, without the backup set after them |
| 5 | Verification failed: a backup set's copy does not match its manifest, or the import log disagrees with Bronze |
