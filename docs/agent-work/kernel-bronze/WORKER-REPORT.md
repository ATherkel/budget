# Kernel/Bronze continuation - worker report

STATUS: ready_for_review

Task: `/root/kernel_bronze_build`, the single implementation bundle continuing
task `01a0b8f4-b59d-7e12-8dbc-5b2851eac4ab`.

Workspace: `C:\Users\Therkel\Documents\GitHub\budget\.tmp\kernel-bronze`, branch
`codex/kernel-bronze`, baseline `387aa3a9e439a73b6e7726ce86aca4f04cc5b8ea`,
source snapshot `../kernel-bronze-baseline-20260922`.

The work is local only: no push, no merge, no deploy, no production data, no
network install. Every commit is authored and committed as
`atherkel-budget-agent[bot] <329499554+atherkel-budget-agent[bot]@users.noreply.github.com>`,
with `Co-Authored-By: Codex deepseek/deepseek-v4.1-flash <noreply@openai.com>`.
Astra owns `PLAN.md` and `CHECKPOINT.md`; this report is the worker's.

## Changed paths (relative to baseline)

| Path | Change |
| --- | --- |
| `kernel/__init__.py` | new, package marker for the Bronze package |
| `kernel/bronze/__init__.py` | the implementation: public contracts plus `danske-csv-v1` ingestion |
| `tests/__init__.py` | new, package marker so discovery imports `tests.test_bronze` |
| `tests/test_bronze.py` | the three original tests unchanged, plus six new tests |
| `.vscode/settings.json` | inherited uncommitted change: unittest discovery, pytest off |
| `.vscode/launch.json` | inherited untracked file: current-file and Bronze-suite debug configs |
| `docs/agent-work/kernel-bronze/PLAN.md` | Astra's plan, committed unchanged |
| `docs/agent-work/kernel-bronze/WORKER-REPORT.md` | this report |

Deliberately left untracked, pre-existing scaffolding from the earlier task that
this continuation did not author: `.python-version`, `pyproject.toml`,
`uv.lock`, `src/kernel_bronze/__init__.py`. The `__pycache__` directories are
untracked and not ignored by `.gitignore`, so every commit above staged explicit
paths only.

Patch size against the baseline for the owned source: 4 files, 1017 insertions
(`kernel/__init__.py`, `kernel/bronze/__init__.py`, `tests/__init__.py`,
`tests/test_bronze.py`).

## Red/green commit chain

| Slice | Red commit (test + recorded failure) | Green commit (behavior) |
| --- | --- | --- |
| cross-account refusal (inherited red) | `b9f7239` test(red) | `ca28c5c` fix(green) |
| malformed payload yields a format failure | `843483a` test(red) | `fae749a` feat(green) |
| unknown source format verdict | `3ac0a4f` test(red) | `0df452f` fix(green) |
| unreadable `Dato` yields a format failure | `0cd6a7a` test(red) | `031cef8` feat(green) |
| declared `covers_through` is bounded | `a980359` test(red) | `13cf0d9` feat(green) |
| missing declaration fallback rules | `82bc74c` test(red) | `bb540e8` feat(green) |
| refused/failed presentation invariants | `31d1438` test(regression), green on first run | - |
| legacy store cannot keep records under a format failure | `0627d40` test(red) | `4f935c8` fix(green) |
| declared field quoting is exact | `c21269f` test(red) | `29fd817` feat(green) |
| a trailing delimiter still needs its quoted field | `ab2bccb` test(red) | `04aac40` fix(green) |
| VS Code discovery configuration | `6f88dc1` chore(vscode) | - |
| plan checkpoint | `8af1b52` docs (Astra authorship) | - |

`31d1438` is honestly labelled: no red was available, because the invariants it
pins (derived source records written with `ON CONFLICT DO NOTHING`, and a repeat
lookup filtered to `outcome = 'stored'`) landed with `13cf0d9`. Nothing was
reverted to manufacture a red.

`04aac40` is the tree of the original green commit for the trailing-delimiter
fix; its message was amended before any push or review because the first version
mis-typed the `Co-Authored-By` model string. The change itself is identical.

Every red above was run before its implementation and failed on the missing
behavior; each green commit records the passing focused run. Two test defects
were found and fixed during the work and are called out in their commit bodies:
the brief-visible first red checkpoint inherited two green slices, and the
missing-declaration test initially read `get_format_failures` after its store
block closed (fixed in `bb540e8`, which did not change the red verdict).

## Behavior delivered

`kernel.bronze.BronzeStore.import_file` now:

- keeps the original public dataclasses and read methods, and every original
  test still passes;
- decodes `danske-csv-v1` strictly as Windows-1252, requires the exact declared
  header, and writes one deterministic `FormatFailure` with zero source records
  for an empty payload, an undecodable byte, an unexpected (including UTF-8)
  header, a malformed CSV shape, or a record whose field count differs from the
  header - while retaining the payload bytes and the import run;
- never echoes source content or the filename in a failure reason, and never
  guesses an encoding;
- resolves the export date from an explicit declaration first and the
  `-YYYYMMDD.csv` suffix otherwise, failing with `ValueError` before any
  persistence when neither is usable or the suffix is not a real date;
- reads `Dato` for one purpose only, the coverage bound, across every row
  whatever its order or `Status`, and turns an unreadable `Dato` into a
  `FormatFailure` rather than an unbounded declaration;
- bounds a declared `covers_through` to `[maximum source Dato, exported_on]`,
  records a refusal as declared rather than clamped, and leaves `repeat_of` null
  on any refused run;
- falls back to `exported_on` marked `exported_on` when no declaration is given,
  refusing instead when the fallback would claim a later reporting period than
  the payload's last transaction, when the payload states no transactions, or
  when the fallback does not reach the last transaction;
- refuses bytes already stored for another account, retains the payload,
  provenance and deterministic source records for refused attempts, and never
  lets a refusal seed account ownership or become a repeat origin;
- validates field quoting on the decoded text before splitting: every field
  opens with a quote, `""` is an escaped quote, and only a comma, a line break
  or the end of the payload may follow a closing quote, with a comma promising
  another quoted field, so an unquoted field, a stray quote in unquoted text, an
  unterminated field, data after a closing quote and a bare trailing delimiter
  are each one deterministic `FormatFailure` with zero records. Line endings are
  deliberately not checked, and a quoted field may still carry an escaped quote
  and a line break of its own;
- reconciles derived cache inside the run's transaction: a payload that does not
  match the declared format has its stale `source_records` deleted and its
  `FormatFailure` recorded, a matching payload has stale failures for that
  format deleted, and every write uses bound `?` parameters with
  `CREATE TABLE IF NOT EXISTS` only. `DELETE` statements touch derived rows
  alone - never `raw_payloads` or `import_runs` - so bytes, provenance and run
  history survive, and `get_source_records` also returns nothing for a payload
  that has a format failure, whatever parser wrote the store;
- fails clearly on an unknown source format instead of guessing.

## Verification

All commands run from `.tmp/kernel-bronze` with
`C:\Users\Therkel\AppData\Local\Programs\Python\Python312\python.exe`. No
TMP/TEMP override was needed: `TemporaryDirectory()` worked throughout.

| Command | Exit | Result |
| --- | --- | --- |
| `python -B -m unittest discover -v -s tests -p 'test_*.py' -t .` | 0 | `Ran 12 tests ... OK` (post-correction) |
| `python -B -m unittest discover -v -s tests -p 'test_*.py' -t . .` (brief's trailing-dot form) | 0 | `Ran 12 tests ... OK` |
| `python -B -m unittest tests.test_bronze.BronzeStoreTests.<slice test> -v` per slice | 1 red, 0 green | recorded in each commit body |
| `python -B -c "import kernel.bronze"` from `tests/` with the workspace on `PYTHONPATH` | 0 | `import ok: kernel.bronze` |
| Astra repro 1, re-run against the corrected code: baseline `BronzeStore` imports the header-mismatched payload, then the current store re-imports it | 0 | `outcome = repeat`, `repeat_of` = the legacy run, `failures = 1`, `records = 0`, bytes intact, the legacy run's twelve stored columns unchanged, `import_runs = 2`, `raw_payloads = 1` |
| Astra repro 2, re-run against the corrected code: `Tekst` written `Ca` + quote + `fe` with no outer quotes | 0 | `outcome = stored`, `failures = 1`, `records = 0`, bytes intact, reason `payload quoting does not match danske-csv-v1: every field must be double-quoted` |
| line-ending tolerance: one payload with LF endings, one CRLF payload with a trailing newline | 0 | both `outcome = stored` with one record and no failure, so the strictness added for quoting did not change line-ending behaviour |
| read-only open, with no re-import, of a lax-parser store | 0 | `records = 1`, `failures = 0`, the documented state before the bytes are presented again |
| acceptance follow-up: seven quoted fields followed by a bare comma, re-run against the final HEAD | 0 | `outcome = stored`, `failures = 1`, `records = 0`, bytes intact, reason `payload quoting does not match danske-csv-v1: a record ends with a comma and no quoted field` |
| `rg -n 'f"""\|f"SELECT\|...' kernel/bronze/__init__.py` | 1 (no match) | no interpolated SQL text |
| `rg -n -i 'drop table\|alter table\|truncate\|vacuum\|delete from raw_payloads\|delete from import_runs' kernel/bronze/__init__.py` | 1 (no match) | the only `DELETE` statements target derived `source_records` and `format_failures`; `PRAGMA foreign_keys = ON` is the only pragma |
| `rg -c 'def test_' tests/test_bronze.py` | 0 | 12 test methods; discovery finds all 12 |

Test discovery and VS Code checks: `.vscode/settings.json` parses and reports
`unittestEnabled=True`, `pytestEnabled=False`, `cwd=${workspaceFolder}` and
`unittestArgs=-v -s tests -p test_*.py -t .`, which is exactly the CLI form
above; `.vscode/launch.json` parses and exposes `Python: Current File and Test
Explorer` (with `PYTHONPATH=${workspaceFolder}`) plus `Bronze tests`. This is a
configuration and import check only - no GUI debugger session was launched, so
the Test Explorer UI itself is unverified.

## Decisions Astra should review

1. **A format-failed run is `outcome='stored'`, not `refused`.** `silver-layer.md`
   reads "import runs with outcome `stored` ... with their source records or
   format failures", and `bronze-agent.md` says an undecodable payload yields a
   `FormatFailure` "rather than a refusal". `stored` here means Bronze stored the
   run; the payload has zero source records, so Silver still quarantines it.
2. **A row whose field count differs from the header is a payload
   `FormatFailure`.** `SourceRecord.fields` is `Mapping[str, str]`, so such a row
   cannot be stored without loss or invention. Silver's "wrong field count"
   validation error is therefore only partly reachable through this seam;
   keeping the payload, zero records and a deterministic verdict was preferred
   over silently truncating. Changing that needs a record type that can carry a
   field list.
3. **Declared export date wins over the filename suffix** (the plan's "as
   before"), which differs from the prototype's `fromName || declared`.
4. **An unknown source format raises `ValueError`** where the inherited code
   raised `NotImplementedError`. Both fail before persistence; the verdict now
   names the unsupported format.
5. **"The proposed coverage is not before the last transaction" is read as the
   Bounded rule applied to the fallback value** (`exported_on`), matching
   `bronze-layer.md` and the reviewed prototype: a same-day export whose last
   `Dato` equals `exported_on` is admitted with the fallback, and the refusal
   case is a payload whose last transaction is *after* the export date. The
   stricter reading - requiring a declaration whenever the export was produced
   on the last transaction's day - would contradict the prototype's 17 passing
   baseline scenarios.
6. **No refusal-reason field was added.** `ImportRun` is unchanged, so a refusal
   states only its outcome; ADR-010's "states its own reason" is unrepresented.
   Adding one needs a contract decision and a read method, so it is not invented
   here.
7. **`Dato` is read as `DD-MM-YYYY`** (the format the existing synthetic fixtures
   use), not the prototype's `DD.MM.YYYY`.
8. **Derived cache is reconciled on presentation, read-side suppression backs
   it up.** Astra's correction 1 is implemented twice over: the transaction
   deletes stale `source_records` when a payload fails its format and stale
   `format_failures` for that format when a payload matches, and
   `get_source_records` returns nothing whenever the payload has a format
   failure. Both leave `raw_payloads` and `import_runs` untouched. A store opened
   read-only that was written by the laxer parser and never re-presented still
   shows that parser's records, because nothing has re-parsed it and no failure
   row exists yet; the first presentation of those bytes replaces them.
9. **Field quoting is validated on the decoded text, not by `csv` alone.**
   `csv.reader(strict=True)` accepts an unquoted field that carries a stray
   quote, which is Astra's correction 2. The format's other stated rules - CRLF
   line endings and no final line break - remain prototype-level notes and are
   deliberately not enforced, so a payload with LF endings or a trailing newline
   is still stored; only quoting and the declared header are strict.
   A comma promises another field, so a record that ends in a bare delimiter is
   rejected even though `csv.reader` counts it as eight fields: the delimiter
   introduces an unquoted empty field. An explicitly quoted empty field (`""`)
   in last position is stored, with `Afstemt` equal to the empty string.

## Limitations and outstanding risks

- The issue #10 manual-decision dependency is deferred as instructed: there is
  no void API, so bytes stored for one account can never be released to another,
  and a voided run cannot be represented.
- Only `danske-csv-v1` exists. There is no rebuild/regeneration entry point for
  derived records or failures, and no CLI/UI.
- The prototype's informational notes (trailing line break, LF line endings) are
  not recorded: `FormatFailure` has no notes channel, so those payloads are
  accepted without a note.
- Refused and format-failed runs are persisted with their payload, which grows
  the database on every rejected presentation. There is no retention policy.
- Derived-cache reconciliation is destructive by design, so a payload_id held
  across presentations can lose its records when a stricter parser rejects the
  bytes. Nothing downstream should cache a `get_source_records` result across an
  import of the same payload.
- The quoting rule is a hand-written scanner rather than the standard library's
  reader, so its behaviour has to keep pace with the declared format if that
  format ever changes.
- No linter, type checker, or CI was run; none is configured in this worktree.
- All evidence is synthetic; no real or private bank export was read.

## Next checkpoint

Astra's first batched review raised two corrections, both are implemented with
their own red/green pairs and re-verified above (`0627d40`/`4f935c8` for legacy
derived records, `c21269f`/`29fd817` for declared quoting). The decisions the
review accepted for this scoped prototype are recorded in
`docs/agent-work/kernel-bronze/PLAN.md`; six earlier decisions above remain open
for the record, and nothing in this bundle depends on them being re-litigated.

The patch is back in review at HEAD after the correction commits. If accepted,
the natural next bundle is the Silver-layer continuation, which owns run
admission, status mapping and `evidence_through`; the deferred manual decisions
(issue #10) unblock cross-account payload reuse.
