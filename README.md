# Budget

A Python-first, self-hostable household budget platform. It is designed around
an immutable Bronze → Silver → Gold data pipeline so reports remain independent
of bank and import format.

Start with the [documentation map](docs/README.md) and the
[delivery roadmap](docs/03-roadmap.md).

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
than a long argument list, and `build`'s own signature is unchanged.

The full pipeline rebuild CLI does not exist yet. `rebuild
[--from bronze|silver|gold]`, the decision-log reader and Gold publishing are
owned by [issue #176](https://github.com/ATherkel/budget/issues/176), which
depends on this work. Until it lands there is deliberately no command that
would silently skip those contracts, and no partial decision-log reader.

`migrate_bronze` refuses the production profile: production is migrated only
by `budget migrate`, which backs the store up first (see below).
`BronzeStore(profile, parsers=...)` accepts an optional mapping for
tests that need two versions of one format; the mapping is copied, and a parser
registered under an ID it does not name is refused.

## Importing an inbox export

`BronzeStore.import_file` only records a run in Bronze. The application
operation `budget.importing.import_inbox_file` is the whole Bronze step of an
import, and the future `import` command calls it once per inbox file under one
writer lock:

```python
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock

with writer_lock(profile) as lock:
    result = import_inbox_file(
        lock,
        profile.inbox / "daily-account" / "danske-20260914.csv",
        Coverage(covers_from=date(2026, 6, 14), covers_through=date(2026, 9, 13)),
    )
```

The file's folder in the inbox is its account, and `accounts.toml` gives that
account's source format. The operation records the run in Bronze, archives the
bytes under `exports/<account_id>/`, mirrors the run in `inputs/imports.jsonl`,
and only then removes the file from the inbox. A refused run is logged with a
copy under `exports/<account_id>/refused/`, and its file stays in the inbox. A
rerun after a crash finishes an earlier stored or repeat run of the same file
instead of adding one, while a refused file is presented again;
[operations.md](docs/architecture/operations.md#importsjsonl-the-import-log)
gives the rules.

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
Nothing imports into production yet: that waits for the `import` command,
which backs up after its Bronze writes.
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
started anew, and no backup is written until it is. A backup is still refused
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
| 3 | The profile file is missing, unreadable, not UTF-8, invalid or of an unknown format |
| 4 | Refused environment: no profile, a production store missing or asked for anew where one or its backup sets exist, a stage not built yet, a store of another profile, stage or schema version, SQLite below the floor, a stores folder that cannot be used, a store another program holds, another command running, a backup set that cannot be written, a store no backup set covers yet or one its backup sets hold gone missing, or a store migrated without the backup set after it |
| 5 | Verification failed: a backup set's copy does not match its manifest, or the import log disagrees with Bronze |
