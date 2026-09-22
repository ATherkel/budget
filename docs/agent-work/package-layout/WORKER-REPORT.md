# Package layout and source-dependent parsing - worker report

STATUS: ready_for_review

Task: `/root/budget_package_layout`.

Workspace: `C:\Users\Therkel\Documents\GitHub\budget\.tmp\kernel-bronze`, branch
`codex/kernel-bronze`, baseline `f1eeda124525b02d5dedc6464814be86cd878f48`. The
bundle's commits are listed below: `137cc07` adds this report, and the
follow-up docs commit that corrects this paragraph is the branch tip at
hand-off. Astra owns `PLAN.md` and `CHECKPOINT.md`; this report and the code are
the worker's.

Local only: no push, no rebase, no amend, no merge, no deploy, no production
data, no network API call. Every commit below is authored and committed as
`atherkel-budget-agent[bot] <329499554+atherkel-budget-agent[bot]@users.noreply.github.com>`
with `Co-Authored-By: Codex deepseek/deepseek-v4.1-flash <noreply@openai.com>`,
set per process with `git -c user.name=... -c user.email=...`, never written to
repository configuration.

## Changed paths

Against the baseline, the changes below (this report excluded) are 20 files,
633 insertions, and 241 deletions.

| Path | Change |
| --- | --- |
| `src/budget/__init__.py` | new package marker, no startup work (1 line) |
| `src/budget/bronze/__init__.py` | thin public re-exports: `BronzeStore` and the four dataclasses (18 lines) |
| `src/budget/bronze/models.py` | the four public dataclasses, unchanged field for field |
| `src/budget/bronze/coverage.py` | bank-independent `covers_through_for` safeguards |
| `src/budget/bronze/store.py` | `BronzeStore`: persistence and import orchestration |
| `src/budget/bronze/parsers/base.py` | `ParserResult` and the `SourceParser` contract |
| `src/budget/bronze/parsers/danske_csv_v1.py` | every Danske rule: encoding, header, quoting, date syntax, filename convention |
| `src/budget/bronze/parsers/registry.py` | the one explicit format-ID-to-parser map |
| `src/budget/bronze/parsers/__init__.py` | thin exports (6 lines) |
| `kernel/__init__.py`, `kernel/bronze/__init__.py` | deleted; the implementation moved into `src/budget/` |
| `src/kernel_bronze/__init__.py` | deleted; the empty competing package is gone |
| `tests/test_bronze.py` | one line: the import moves to `budget.bronze` (verified below) |
| `tests/test_source_parsers.py` | new: the parser-contract and registry tests |
| `pyproject.toml` | distribution is `budget`, the nonexistent `kernel-bronze` script and the unused pytest dev group are gone, owner metadata and Python floor kept |
| `uv.lock` | regenerated to match; one package, no dev dependencies |
| `.gitignore` | `dist/` and `build/` ignored |
| `.vscode/settings.json` | `python.defaultInterpreterPath` points at `.venv` |
| `.vscode/launch.json` | the stale `PYTHONPATH` workaround is removed; current-file and suite configs kept |
| `README.md` | install, test, build, layout, and format-extension instructions |
| `docs/developers/source-parsers.md` | the parser contract, the registry, and the open multi-format decisions |
| `docs/agent-work/package-layout/WORKER-REPORT.md` | this report |

`docs/agent-work/package-layout/PLAN.md` is still untracked and untouched: the
automatic approval review rejected the worker committing a planning document as
"not one of the explicitly requested red/green implementation commits", so it
is left exactly as Astra wrote it for Astra to commit.

## Commit chain

| Commit | Kind | Content |
| --- | --- | --- |
| `3e5e419` | refactor | move `kernel.bronze` into the installable `budget` package; drop the dead CLI and the pytest dev dependency; VS Code interpreter and `PYTHONPATH` fix |
| `e19fa1b` | test(red) | declare the source-parser selection seam |
| `9d396da` | feat(green) | split parsing into a contract, a registry, and `danske_csv_v1` |
| `dc9f7bf` | test(red) | let the declared parser own its export-date filename convention |
| `c56c1c5` | feat(green) | read the export date through the declared parser |
| `212225d` | docs | install, test, and extend the budget package (`README.md`, parser guide, package docstring) |
| `137cc07` | docs | this report, plus the follow-up commit that corrects its tip reference |

`3e5e419` and `212225d` are honestly un-red: the first is a behavior-preserving
move (`docs/agents/tdd.md`, *Exceptions*), the second is documentation plus a
docstring. Neither manufactured a failing test, and the two real slices each
have a recorded red run before their green commit.

### Red/green evidence

| Slice | Red command and result (before the green commit) | Green command and result |
| --- | --- | --- |
| parser contract and registry | `uv run --offline python -m unittest tests.test_source_parsers -v` → exit 1, `ModuleNotFoundError: No module named 'budget.bronze.parsers'`, `Ran 1 test ... FAILED (errors=1)` (`.tmp/logs/01-red-parser-seam.txt`) | `uv run --offline python -m unittest discover -v -s tests -p 'test_*.py' -t .` → exit 0, `Ran 16 tests in 0.376s`, `OK` (`.tmp/logs/02-green-parser-seam.txt`) |
| parser-owned filename convention | `uv run --offline python -m unittest tests.test_source_parsers -v` → exit 1, `AttributeError: 'DanskeCsvV1Parser' object has no attribute 'exported_on_from_filename'`, `Ran 6 tests ... FAILED (errors=2)` (`.tmp/logs/03-red-filename-convention.txt`) | same discovery command → exit 0, `Ran 18 tests in 0.367s`, `OK` (`.tmp/logs/04-green-filename-convention.txt`) |

Each red was produced by running the new test against the committed parent
state, and each red failed on the missing behavior, not on setup.

## Behavior delivered

- One installable application package, `budget`, discovered from `src/budget`
  by the existing `uv_build` backend. `from budget.bronze import BronzeStore`
  works from an installed wheel or sdist, not only from the repository root.
- The four public dataclasses (`RawPayload`, `ImportRun`, `SourceRecord`,
  `FormatFailure`), the SQLite schema, the persisted format, and every read
  method are unchanged. The legacy-store fixture test still passes.
- `budget.bronze.parsers.base` declares the small typed contract: exact bytes
  in; `ParserResult.matched(records, last_transaction_date)` or
  `ParserResult.failed(reason)` out. A failure exposes no records by
  construction, and a reason never repeats source content or the filename.
- `budget.bronze.parsers.registry` is the only selection point: one explicit
  map, no auto-detection, no entry points, no mutable registration. An
  undeclared ID is refused by name before the store reads the file.
- `budget.bronze.parsers.danske_csv_v1` owns the encoding (strict
  Windows-1252), the declared header, the all-quoted field shape (including the
  bare-trailing-delimiter refusal), the `DD-MM-YYYY` transaction date, and the
  `-YYYYMMDD.csv` export-date convention. An unrecognised filename yields
  `None` so the operator can declare a date; a recognisable-but-impossible
  suffix raises `ValueError` without repeating any digit of the private name.
- `budget.bronze.store` names no bank, field, encoding, or date syntax; it
  resolves the export date through the selected parser, calls `parse`, and
  bounds the declaration with `budget.bronze.coverage`.
- `docs/developers/source-parsers.md` records the extension contract and the
  decisions this bundle deliberately does not take: `SourceRecord.fields` is
  string-only, so richer (JSON/API) payloads need a record-contract decision;
  source records are keyed by `(payload_id, record_ordinal)`, so a second format
  that can read the *same bytes* requires scoping the derived cache by
  `source_format`; acquisition, authentication, and pagination stay outside
  pure bytes parsing. No future adapter, schema migration, or registration hook
  was added.

## Verification

Run from `C:\Users\Therkel\Documents\GitHub\budget\.tmp\kernel-bronze` with the
working interpreter `C:\Users\Therkel\AppData\Local\Programs\Python\Python312\python.exe`
(3.12.3) and `uv 0.12.13`. Full logs are in the ignored `.tmp/logs/` directory.

| Command | Exit | Result |
| --- | --- | --- |
| `uv run --offline python -m unittest discover -v -s tests -p 'test_*.py' -t .` | 0 | `Ran 18 tests in 0.381s`, `OK` - the 12 original tests unchanged plus 6 new (`14-final-unittest.txt`) |
| `git diff f1eeda1 HEAD -- tests/test_bronze.py` | 0 | one changed line: `from budget.bronze import BronzeStore`; assertions and fixtures untouched |
| `uv run --offline python -c "import budget, budget.bronze; print(...)"` | 0 | `budget` resolves to `src\budget\__init__.py` through the editable install |
| `uv run --offline python tests/test_source_parsers.py -v` | 0 | `Ran 6 tests`, `OK` - a direct current-file run works with the venv interpreter |
| `python.exe -B -c "import budget"` on the *uninstalled* system interpreter | 1 | `ModuleNotFoundError: No module named 'budget'` - nothing on `PYTHONPATH` or in `sys.path` is hiding a packaging error |
| `.vscode/settings.json` and `.vscode/launch.json` parsed with `ConvertFrom-Json` | 0 | interpreter `${workspaceFolder}/.venv/Scripts/python.exe`; `unittestEnabled=True`, `pytestEnabled=False`, args match the CLI above; both launch configs carry no `env.PYTHONPATH` |
| `uv lock --check` | 0 | `Resolved 1 package` - lock matches `pyproject.toml` |
| `git diff --check` | 0 | no whitespace errors |
| `rg -n -i -e 'kernel' -e 'kernel_bronze' src tests README.md pyproject.toml uv.lock .vscode .gitignore` | 1 | no match: no competing package name or alias survives in the working tree |
| `rg -n -i -e 'danske' -e 'dato' -e 'csv' -e 'cp1252' -e 'YYYYMMDD' -e 'strptime' src/budget/bronze/store.py` | 1 | no match: the store carries no bank, CSV, encoding, or date specifics |
| `git ls-files kernel src/kernel_bronze` | 0 | empty - both obsolete layouts are deleted from the index |
| init line counts | 0 | `src/budget/__init__.py` 1 line, `bronze/__init__.py` 18, `parsers/__init__.py` 6 |

### Build, contents, and installation

| Command | Exit | Result |
| --- | --- | --- |
| `UV_CACHE_DIR=%TEMP%\budget-uv-cache uv build --offline` | 0 | `Successfully built dist\budget-0.1.0.tar.gz` (8,791 bytes) and `dist\budget-0.1.0-py3-none-any.whl` (12,229 bytes) (`11-final-build.txt`) |
| `tar -tf dist/budget-0.1.0-py3-none-any.whl` | 0 | only `budget/`, `budget/bronze/**`, `budget/bronze/parsers/**`, and `budget-0.1.0.dist-info/{WHEEL,METADATA,RECORD}`; no `kernel*`, no `entry_points.txt`, so no console script |
| `tar -tf dist/budget-0.1.0.tar.gz` | 0 | `pyproject.toml`, `README.md`, and `src/budget/**`; no tests, no caches, no `.tmp`, no build artifacts |
| `Get-ChildItem <fresh venv>\Scripts` | 0 | only `python.exe`, `pythonw.exe` (plus activate helpers): `kernel-bronze.exe` is absent |
| `uv venv` + `uv pip install --offline --no-deps dist/budget-0.1.0-py3-none-any.whl` in `%TEMP%\budget-final-wheel` | 0 | `Installed 1 package`, `+ budget==0.1.0` (`12-final-install-budget-final-wheel.txt`) |
| `uv venv` + `uv pip install --offline --no-deps dist/budget-0.1.0.tar.gz` in `%TEMP%\budget-final-sdist` | 0 | wheel built from the sdist offline and installed (`12-final-install-budget-final-sdist.txt`) |
| synthetic smoke test, run from `%TEMP%\budget-wheel-smoke` with no `PYTHONPATH`, once per environment | 0 each | `budget imported from ...\site-packages\budget\__init__.py`; `kernel` and `kernel_bronze` are not importable; a synthetic payload imported, its file deleted, the store reopened, and `Tekst`, `Beløb`, byte length, export date, and coverage read back intact; identical `payload_id 5ae39920...abeee` from both artifacts (`13-final-smoke-*.txt`) |

Notes on tooling. The sandbox cannot write uv's default cache
(`C:\Users\Therkel\AppData\Local\uv\cache`), so `UV_CACHE_DIR` points at
`%TEMP%\budget-uv-cache`, outside the checkout. The first build used a cache
inside the working tree and uv warned it "may be included in distributions";
the cache was moved out and the build re-run, and the shipped sdist was
inspected to confirm it contains only `pyproject.toml`, `README.md`, and
`src/budget/**`. Everything was resolved offline from the cache; no global
install, no paid probe, no new runtime dependency, and no network API call was
made.

Not verified: a GUI VS Code session (Test Explorer, F5) was not launched, so
the JSON, interpreter path, discovery arguments, and direct-file run are
configuration-and-command evidence only.

## Outstanding risks and limitations

- Only `danske-csv-v1` exists. `nordea-csv-v1`, `danske-api-v1`, and
  `danske-csv-v2` are naming examples, not implementations.
- `SourceRecord.fields` is string-only, so a nested payload cannot be presented
  faithfully yet; the guide records this as a contract decision rather than
  pretending an API format would fit.
- Derived source records are still keyed by `(payload_id, record_ordinal)`
  while failures are keyed by `(payload_id, source_format)`. That remains
  unambiguous for one declared format and one payload owner, and the guide
  states what must be decided before a second format can read the same bytes.
- There is still no rebuild entry point for derived records or failures, no
  CLI, and no retention policy for refused or failed runs - all unchanged from
  the accepted Bronze baseline.
- `docs/agent-work/kernel-bronze/*` still describes the previous `kernel/`
  layout. Those are historical reports and were deliberately left as history.
- The package docstring changed from "Household finance kernel." to
  "Household finance application package."; that one-line edit is inside the
  docs commit.

## Decisions for Astra

1. **PLAN.md is uncommitted.** The automatic approval review refused a
   worker-authored commit of a planning document, so it is left untracked for
   Astra. No content was edited.
2. **Distribution description.** `pyproject.toml`'s placeholder description
   ("Add your description here") became the README's first line. Author, email,
   `readme`, and `requires-python` are unchanged; `version` stays `0.1.0`.
3. **No packaging test in the suite.** The install/smoke verification is a
   recorded out-of-band command rather than a unit test, because a test that
   builds and installs a wheel needs a second environment and network-free
   build tooling. Say so if Astra wants it promoted into the suite.
4. **Absent filename convention.** A filename the format does not recognise
   yields `None` and the store asks for a declaration; a
   recognisable-but-impossible suffix raises `ValueError` whose message
   carries no digit of the private name. This keeps `original_filename` out of
   logs, and differs slightly from the earlier message that included the
   parsed digits via `strptime`.

## Next checkpoint

Nothing in this bundle is unfinished. The natural next work is the Silver-layer
continuation, which would consume `budget.bronze` through its public seam.
