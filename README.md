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
| `src/budget/bronze/` | Bronze: raw payloads, import runs, source records |
| `src/budget/bronze/parsers/` | the parser contract, the registry, and one module per source format |
| `tests/` | `unittest` suites, discovered from the repository root |
| `docs/` | contracts, decisions, and domain documents |

## Adding a source format

Parsing is separated by source, representation, and version:
[docs/developers/source-parsers.md](docs/developers/source-parsers.md) describes
the contract, how to register a format, and what is deliberately not solved yet.

## Storage and profiles

A profile is an immutable value that names the folder its stage stores live in.
Nothing is selected implicitly, and a test profile refuses any path outside the
temporary directory it was built from:

```python
from budget.bronze import BronzeStore, migrate_bronze
from budget.profiles import Profile

profile = Profile(name="development", stores=Path("dev-stores"))
migrate_bronze(profile)

with BronzeStore(profile) as store:
    run = store.import_file(
        source,
        declared_account_id="daily-account",
        source_format="danske-csv-v1",
        covers_through=date(2026, 9, 13),
    )
```

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
