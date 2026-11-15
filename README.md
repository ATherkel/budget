# Budget

A Python-first, self-hostable household budget platform. An immutable
Bronze → Silver → Gold pipeline keeps reports independent of bank and import
format.

## Install and test

`uv` manages the environment. Python 3.12 or newer is required.

```powershell
uv sync
uv run pytest
```

`uv sync` creates `.venv/` and installs the `budget` command from `src/budget`
in editable mode; that is the whole setup. The real-browser dashboard tests
launch the installed Google Chrome, so they need Chrome and download no
browser. `uv build` writes a wheel and an sdist into the ignored `dist/`
folder; installing that wheel proves the package works outside the checkout.

Every Python change must pass the quality gate before it is committed, and CI
runs the same four checks:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run complexipy
```

[code-quality.md](docs/agents/code-quality.md) says what each check enforces.

In VS Code, pick `.venv/Scripts/python.exe` with **Python: Select
Interpreter** if the workspace was already using system Python; the workspace
setting only supplies a default for a window with no interpreter selected.

## Layout

| Path | Contents |
| --- | --- |
| `src/budget/` | the application package |
| `src/budget/cli.py` | the `budget` command line |
| `src/budget/bronze/` | Bronze: raw payloads, import runs, source records |
| `src/budget/bronze/parsers/` | the parser contract, the registry, and one module per source format |
| `examples/` | walkthrough scripts on synthetic data |
| `tests/` | the test suites, run from the repository root |
| `docs/` | contracts, decisions, and domain documents |

## Everyday use

Every command except `demo` needs a profile file, named by `--profile` or the
`BUDGET_PROFILE` environment variable. There is no default profile. This
PowerShell writes a development profile outside the repository, and refuses
to replace one that exists:

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
$env:BUDGET_PROFILE = "$env:APPDATA\budget\development.toml"
```

A store holds real bank data, so keep stores outside the checkout and outside
a synchronised folder such as OneDrive.
[Profiles](docs/architecture/operations.md#profiles) lists every key a profile
file may hold and where production lives.

| Command | What it does |
| --- | --- |
| `budget migrate` | Creates or upgrades the Bronze, Silver and Gold [stores](docs/architecture/operations.md#stores) |
| `budget import` | Imports each export saved in `inbox\<account_id>\`, then rebuilds and publishes: [the monthly import](docs/architecture/operations.md#w1-the-monthly-import) |
| `budget review` | Lists what needs a decision: [settling a review item](docs/architecture/operations.md#w2-settling-a-review-item) |
| `budget find`, `budget decide` | Finds a transaction and records a manual decision about it: [commands](docs/architecture/operations.md#commands) |
| `budget status` | Shows whether the figures are complete: [completeness outputs](docs/architecture/operations.md#completeness-outputs) |
| `budget rebuild`, `budget undo` | Builds the stages again, or returns to the previous publication: [commands](docs/architecture/operations.md#commands) |
| `budget backup`, `budget restore` | Writes or restores a backup set of production: [backup and restore](docs/architecture/operations.md#backup-and-restore) |
| `budget set-passphrase`, `budget serve` | Sets the login and starts the read-only dashboard: [dashboard access](docs/architecture/operations.md#dashboard-access) |
| `budget demo` | Serves a synthetic dashboard from a new folder, with no profile: [testing by hand](docs/developers/manual-testing.md#dashboard) |

The [command reference](docs/architecture/operations.md#commands) covers every
command and option,
[exit codes](docs/architecture/operations.md#exit-codes) says what each exit
status means, and
[failure and retry](docs/architecture/operations.md#failure-and-retry) says
what to do when a command refuses.

## Where next

- [Documentation map](docs/README.md): every contract, decision and domain
  document, and what is built.
- [Delivery roadmap](docs/03-roadmap.md).
- [Testing by hand](docs/developers/manual-testing.md): try each feature on
  your development profile.
- [Example walkthroughs](docs/developers/silver-walkthrough.md): an import and
  a review on synthetic data, with the transcript.
- [Source parsers](docs/developers/source-parsers.md): the parser contract and
  how to add a source format.
