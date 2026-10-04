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

`migrate_bronze` is the only operation that creates or upgrades a store. It
applies the numbered SQL files in `src/budget/migrations/bronze/`, which ship
inside the installed wheel and sdist so an installation can migrate without a
source checkout, and it records both `PRAGMA user_version` and a one-row
`store_identity` naming the profile and stage. Opening a store never creates or
changes the schema: it requires an existing file, `mode=rw`, a version this code
knows, and a matching identity, and it sets `foreign_keys = ON`,
`busy_timeout = 5000` and `synchronous = FULL`. A new store is created in WAL
mode.

The production profile refuses to migrate until the backup and command work
lands (issue #120), so these commands are for development and test profiles
today. `BronzeStore(profile, parsers=...)` accepts an optional mapping for
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
be absolute, and the inbox and exports folders may not overlap. `profile` is `development` or `production`.

```powershell
budget --profile "$env:APPDATA\budget\development.toml" migrate
```

`migrate` creates or upgrades the profile's Bronze store; `--stage bronze`
names it explicitly, and `--stage silver` or `--stage gold` is refused until
those stores exist. A writing command holds the operating system's lock on
`budget.lock` in the stores folder for its whole run, so a second one refuses at
once. On Windows the lock of a command that was killed or crashed is released a
moment late, so an immediate rerun can report another command running; rerun
it shortly. Production migration is refused until issue #120 adds the backup it
needs.

| Exit | Meaning |
| --- | --- |
| 0 | Done |
| 1 | Unexpected error: a defect, such as a broken packaged migration |
| 2 | Usage error, including a command that is not built yet |
| 3 | The profile file is missing, unreadable, not UTF-8, invalid or of an unknown format |
| 4 | Refused environment: no profile, production, a stage not built yet, a store of another profile or schema version, SQLite below the floor, a stores folder that cannot be used, a store another program holds, or another command running |
