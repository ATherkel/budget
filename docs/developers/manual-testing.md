---
type: developers
---
# Testing by Hand

How to try each feature on `main` with your development profile,
`$env:APPDATA\budget\development.toml`. Its stores are derived and
scrappable. Commands are PowerShell, run from a checkout of `main` in one
window, so the variables from [Set up](#set-up) stay set.

Each feature has its own section. A feature that changes what you can try by
hand updates its section here as part of its acceptance criteria. A section
marked "to be filled" waits on the issue it names.

## Set up

Close DB Browser for SQLite if it has a dev store open, then run each block in
turn.

```powershell
uv sync
```

Use `BUDGET_PROFILE` if it is set, otherwise the usual development profile:

```powershell
$devProfile = $env:BUDGET_PROFILE ?? "$env:APPDATA\budget\development.toml"
$env:BUDGET_PROFILE = $devProfile
```

Check that it is a development profile. This prints `development`; stop if
it prints anything else:

```powershell
uv run python -c "import sys,tomllib; print(tomllib.load(open(sys.argv[1],'rb'))['profile'])" $devProfile
```

Read the profile's folders:

```powershell
$paths = uv run python -c "import json,sys,tomllib; print(json.dumps(tomllib.load(open(sys.argv[1],'rb'))['paths']))" $devProfile | ConvertFrom-Json
$stores = $paths.stores; $inputs = $paths.inputs; $exports = $paths.exports; $inbox = $paths.inbox
$ranges = "$env:LOCALAPPDATA\budget\dev-household\ranges.toml"
```

`inputs` must hold `accounts.toml`, `taxonomy.toml` and `rules.toml`. Save
what the tests change, so [Clean up](#clean-up) can put it back:

```powershell
$backup = "$env:LOCALAPPDATA\budget\manual-test-backup"
New-Item -ItemType Directory -Force $backup | Out-Null
Copy-Item $devProfile, "$inputs\taxonomy.toml", "$inputs\rules.toml", "$inputs\accounts.toml", "$inputs\decisions.jsonl" $backup
```

### If an older profile fails

- **`migrate` fails with "no such table".** The store predates its stage's
  first schema. Delete `$stores\silver.db` or `$stores\gold.db` and migrate
  again; both are rebuilt from Bronze.
- **The decision log is refused.** A line without a final line feed, or a
  placeholder decision, breaks it. Start it empty with
  `Set-Content "$inputs\decisions.jsonl" -Value '' -NoNewline`.
- **No categories or rules.** [Rules and decisions](#rules-and-decisions)
  need at least one rule and two categories:

  ```powershell
  Set-Content "$inputs\taxonomy.toml" -Value @'
  format = 1

  [group.food]
  name = "Food"
  direction = "expense"

  [category.groceries]
  name = "Groceries"
  group = "food"

  [category.eating-out]
  name = "Eating out"
  group = "food"
  '@
  ```

  ```powershell
  Set-Content "$inputs\rules.toml" -Value @'
  format = 1

  [[rule]]
  id = "r-netto"
  when.description_contains = "NETTO"
  then.category = "groceries"
  '@
  ```

## Migrate and build

```powershell
uv run budget migrate
uv run budget rebuild --from silver
```

Expect a `Run <id>  <account>  accepted` line per import run, the Silver
counts, then `Gold     published publication N`. Then:

| Do | Expect |
| --- | --- |
| `uv run budget rebuild` | `the recipe is unchanged; nothing was published (publication N stays current)` |
| `uv run budget rebuild --from bronze` | Bronze, Silver and Gold lines; Gold unchanged |
| Add `[gold]` with `late_booking_days = 0` to the profile, then `rebuild` | A new publication; recent months' "late bookings settled" can flip |

## Rules and decisions

Change `"NETTO"` to `"netto"` in `rules.toml`, or add a comment, then
`uv run budget rebuild`. Expect unchanged: the meaning is the same.

The decisions below assume an empty log. Pick the latest MENY purchase in the
current publication (the highest `publication_id` while there is no undo):

```powershell
$id = uv run python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); p=c.execute('select max(publication_id) from publications').fetchone()[0]; print(c.execute(""select transaction_id from transactions where publication_id=? and description like 'MENY%' order by transaction_date desc limit 1"",(p,)).fetchone()[0])" "$stores\gold.db"
```

Classify it as eating out. Expect a new publication, with the amount under
Eating out:

```powershell
Add-Content "$inputs\decisions.jsonl" "{`"format`": 1, `"entry`": 1, `"decision_id`": `"d-0001`", `"recorded_at`": `"2026-10-27T18:00:00Z`", `"kind`": `"classify`", `"targets`": [`"$id`"], `"category`": `"eating-out`", `"reason`": `"dev test`", `"supersedes`": []}"
uv run budget rebuild
```

Retract it. Expect a new publication whose figures match the one before the
decision:

```powershell
Add-Content "$inputs\decisions.jsonl" '{"format": 1, "entry": 2, "decision_id": "d-0002", "recorded_at": "2026-10-27T18:05:00Z", "kind": "retract", "targets": [], "reason": "dev test", "supersedes": ["d-0001"]}'
uv run budget rebuild
```

## Refusals

Each exits 3 and changes no store; put the file back and `rebuild` reports
unchanged.

| Do | Expect |
| --- | --- |
| Append `this is not toml` to `taxonomy.toml`, then `rebuild --from silver` | Exit 3 |
| Set an account's `closed_on` before its latest transaction, then `rebuild` | Exit 3, naming the account |
| Same, then `import` with a file in the inbox | Exit 3 before the inbox is touched |

## Import

Put an export in `$inbox\<account_id>\`, then:

```powershell
uv run budget import --ranges $ranges
```

Expect `[1] <account>  stored`, the Silver line, then Gold published, and the
file gone from the inbox. With no fresh export from the bank, copy an archived
one from `$exports\<account_id>\`: it is stored again and Gold reports
unchanged. The README's
[import outcomes](../../README.md#importing-the-inbox-budget-import) list each
line and exit status.

## Review

`uv run budget review` lists open review items and quarantined runs, and
prints nothing when none are open.

## Dashboard

Your dev profile needs `[dashboard]` and a passphrase
(`uv run budget set-passphrase`). Run `uv run budget serve`, open the address
it prints and log in. Check the account picker, the month picker and the
monthly overview against the current publication.

Without your profile, `uv run budget demo` serves synthetic data; see the
README's [dashboard section](../../README.md#the-dashboard-budget-serve).

## Restore and dev refresh

To be filled by #121.

## Status and check

To be filled by #296 and #303.

## Clean up

Put the profile and inputs back, and build from them:

```powershell
Copy-Item "$backup\$(Split-Path $devProfile -Leaf)" $devProfile
Copy-Item "$backup\taxonomy.toml", "$backup\rules.toml", "$backup\accounts.toml", "$backup\decisions.jsonl" $inputs
uv run budget rebuild --from silver
```

Then remove the backup:

```powershell
Remove-Item $backup -Recurse
```

Keep Bronze and `imports.jsonl` as they are: they record real runs.
