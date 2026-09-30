# Bronze live-test scripts

Throwaway tools from live-testing PR #113 against real Danske exports on
2026-09-29 and 2026-09-30. They are parked on this branch so they are not lost.
They are **not** meant to be merged: they fail the repository's quality gate
(`print`, missing copyright headers and docstrings, f-string SQL), and would need
a rewrite before any pull request.

They prototype behaviour that is specified in issues:

| Script behaviour | Issue |
| --- | --- |
| Read a development profile TOML, `accounts.toml` and `inbox\<account_id>\` | #116, #117 |
| Skip a file whose account number contradicts `bank_account_number` | #149 |
| Stop on identical bytes under different accounts, then ask `Continue anyway? [y/N]` | #150 |
| Print why a run was refused (re-derived, not read from the store) | #151 |

## Use

Run from a checkout that has `budget` installed (`uv sync`). Nothing moves in the
household folder: no archive step and no `imports.jsonl` line.

```powershell
uv run python scripts/live-test/live_bankudtraek.py "$env:APPDATA\budget\development.toml" <from> <through>
uv run python scripts/live-test/show_runs.py
```

- `<from>` and `<through>` are the inclusive range chosen in netbank (#143). An
  account exported with another range goes in `RANGE_OVERRIDES`.
- The profile must be a `development` profile. Its `[paths]` name `stores`,
  `inbox` and `inputs`.
- `show_runs.py` opens `%LOCALAPPDATA%\budget\dev\bronze.db` read-only and lists
  every run with its declared range and last transaction date.

Keep the store outside the checkout and outside OneDrive: it holds real bank
data, and a synchronised SQLite file can be corrupted.
