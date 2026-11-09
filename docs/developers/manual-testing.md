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
counts, then `Gold     published publication N (cause build)` and a `Changes`
line comparing it with the previous publication. Then:

| Do | Expect |
| --- | --- |
| `uv run budget rebuild` | `the recipe is unchanged; nothing was published (publication N stays current)` |
| `uv run budget rebuild --from bronze` | Bronze, Silver and Gold lines; Gold unchanged |
| Add `[gold]` with `late_booking_days = 0` to the profile, then `rebuild` | A new publication; recent months' "late bookings settled" can flip |

## Rules and decisions

Change `"NETTO"` to `"netto"` in `rules.toml`, or add a comment, then
`uv run budget rebuild`. Expect unchanged: the meaning is the same.

Decisions are recorded with `budget decide`, which checks each one, appends
it to `decisions.jsonl` and rebuilds. Never edit the log by hand. The
decisions below assume an empty log, so the first is `d-0001`.

List what is waiting to be classified:

```powershell
uv run budget review --kind unclassified
```

Each item shows its transaction on a `target` line, with its 8-character
handle first:

```text
  target b6a05be4  joint-current  2026-03-02  -120.00 DKK  "MENY HOVEDGADE"  bank category Mad
```

Pick one, such as a MENY purchase, and put its handle in `$handle`:

```powershell
$handle = "b6a05be4"
```

Classify it as eating out:

```powershell
uv run budget decide classify $handle eating-out --reason "dev test"
```

Expect exit 0, then the completeness output after lines like these, with your
own amount, month and publication number:

```text
Recorded d-0001.
Gold     published publication 2 (cause build)
Changes  2026-03 joint-current: expenses +120.00 DKK; category eating-out +120.00 DKK; group food +120.00 DKK; unclassified out +120.00 DKK; unclassified count -1
Review  1 unclassified closed
```

Each rejection exits 3, starts with
`budget: the decision was rejected; nothing was recorded:` and leaves the log
as it was:

| Do | Expect |
| --- | --- |
| `uv run budget decide classify $handle groceries --reason "dev test"` | Rejected: `<transaction_id> is already decided by d-0001, which supersedes does not list` |
| The same with `--supersedes d-0001` | Exit 0, `Recorded d-0002.`; `Changes` moves the amount from eating-out to groceries |
| `uv run budget decide classify $handle no-such-category --supersedes d-0002 --reason "dev test"` | Rejected: `category "no-such-category" is not in the taxonomy` |
| `uv run budget decide classify zzzzzzzz groceries --reason "dev test"` | Rejected: `no transaction in Silver has the handle "zzzzzzzz"` |

Retract it. Expect exit 0, `Recorded d-0003.`, and a publication whose figures
match the one before d-0001: `Changes` reverses the first decision's line, and
`Review  1 unclassified opened`.

```powershell
uv run budget decide retract --supersedes d-0002 --reason "dev test"
```

### Voiding an import run

A run declared with the wrong range is voided, then its export is imported
again with the right one. Take the newest run from the import log, and void
it:

```powershell
$run = (Get-Content "$inputs\imports.jsonl" | Select-Object -Last 1 | ConvertFrom-Json).import_run_id
uv run budget decide void-import-run $run --reason "dev test: wrong range"
```

Expect `Recorded d-0004.`, then the Silver lines, because a Silver decision
rebuilds from Silver. The run is shown as `unrecorded`, and `Changes` takes
its transactions out. Copy its export from `$exports\<account_id>\` back
into `$inbox\<account_id>\`, then import it with a corrected range in
`$ranges`. Expect `[1] <account>  stored` as a new run with the new
`covers_from` in `imports.jsonl`. Decisions on its transactions apply again,
because the transactions keep their IDs.

The other kinds take their own options (`pair <handle> <handle>`,
`one-sided-transfer <handle> --counterpart <account_id>`,
`same-transaction <handle> --record <payload_id>:<ordinal>`); see
`operations.md`, *Commands*.

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

Both read production's backup sets. Your dev profile needs `upstream_backups`
under `[paths]`, naming production's `backups` folder; development only
reads it.

### Dev refresh

```powershell
uv run budget dev refresh
```

Expect `restored backup set <name> into upstream (read-only)`, and the
read-only copies in `$stores\upstream\`. Your own stores and inputs are left
alone. `--inputs` also replaces your inputs with the set's copy, so run it only
after [Set up](#set-up) has saved them.

`--writable` replaces your own stores with the set's, relabelled as
development, to rehearse a `migrate` on production's data. It replaces your
Bronze too, so copy your stores aside first and put them back after:

```powershell
$devStores = "$env:LOCALAPPDATA\budget\manual-test-stores"
Copy-Item $stores $devStores -Recurse
uv run budget dev refresh --writable
```

Expect `restored backup set <name> into development's own stores (writable)`.

### Restore

`restore` runs on production only, so try it on a scratch production profile
that has a copy of one set and no stores. It builds as production, so run it
from a clean checkout of `main`:

```powershell
$scratch = "$env:LOCALAPPDATA\budget\manual-test-restore"
$set = Get-ChildItem $paths.upstream_backups -Directory | Sort-Object Name | Select-Object -Last 1
New-Item -ItemType Directory -Force "$scratch\backups", "$scratch\inputs", "$scratch\inbox", "$scratch\exports" | Out-Null
Copy-Item $set.FullName "$scratch\backups" -Recurse
Copy-Item "$exports\*" "$scratch\exports" -Recurse
Set-Content "$scratch\production.toml" -Value @"
format = 1
profile = "production"

[paths]
stores = '$scratch\stores'
inputs = '$scratch\inputs'
inbox = '$scratch\inbox'
exports = '$scratch\exports'
backups = '$scratch\backups'
"@
$env:BUDGET_PROFILE = "$scratch\production.toml"
uv run budget restore
```

Expect a `put back inputs/<file> from the backup set` line per input, one
line saying the decision log or import log was missing for each that the set
held, the Gold line, `restored backup set <name>`, and `backup set <new name>
written`. A profile with no `backups` path writes no closing set, so that last
line is absent. Then:

| Do | Expect |
| --- | --- |
| `uv run budget restore` again | Exit 4: the stores folder still holds `bronze.db` |
| `uv run python -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select * from recovery_boundaries').fetchall())" "$scratch\stores\gold.db"` | One row naming the set |

Point `BUDGET_PROFILE` back at your dev profile and remove the scratch profile:

```powershell
$env:BUDGET_PROFILE = $devProfile
Remove-Item $scratch -Recurse
```

After `--writable`, put your own stores back:

```powershell
Remove-Item $stores -Recurse
Move-Item $devStores $stores
```

## Status and check

`status` reads the stores and writes nothing, so it is safe at any point:

```powershell
uv run budget status
```

Expect these blocks, in order. `Published figures: publication N (current)`
with a coverage line per account and month (the latest 12 reporting months),
`Unclassified money, by account and month` with money in, money out and a
count per account and month, `Open review items` with Silver's and Gold's on
separate lines, and `Import evidence (operational, apart from published
figures)` with each account's latest export date, evidence-through date and
quarantined runs. Then:

| Do | Expect |
| --- | --- |
| `uv run budget rebuild`, then `uv run budget status` | The last lines of `rebuild` are the same block `status` prints |
| `uv run budget import --ranges $ranges` with an export in the inbox | The same block at the end, after the `Changes` lines |
| `uv run budget rebuild` with nothing changed | `nothing was published`, then the same block |
| Move `gold.db` aside, then `uv run budget status`, then put it back | `Published figures: unavailable, nothing is published`; the import evidence still shows; nothing is created |

`import` and `rebuild` print the block to the terminal only. It never changes
their exit codes and never reaches `commands.jsonl`.

`check` validates every input file and the decision log, and compares the log
with the prefix every Gold recipe recorded. It builds nothing, writes nothing
and takes no lock, so it too is safe at any point. Reading `gold.db` may leave
`gold.db-wal` and `gold.db-shm` beside it. SQLite keeps these for every
reader in WAL mode, and they are harmless (see
[WAL sidecar files left by read-only reads](../../.out-of-scope/wal-sidecars-on-read-only-reads.md)).

```powershell
uv run budget check; $LASTEXITCODE
```

On valid inputs it prints `No problems found.` and `0`. Then break one thing
at a time, run the same command, and put the file back before the next row:

| Break | Expect | Put back |
| --- | --- | --- |
| Add `[category.broken]` with `name = "Broken"` and `group = "nowhere"` to `taxonomy.toml` | `taxonomy.toml: category "broken": group "nowhere" is not declared`, then `1 problem. Nothing was built.` and `3` | `Copy-Item "$backup\taxonomy.toml" $inputs` |
| The same, and a second error in `rules.toml` | Both problems, then `2 problems. Nothing was built.` and `3`: a refused file does not hide the other | Copy both back from `$backup` |
| `Add-Content "$inputs\decisions.jsonl" '{"format": 1' -NoNewline` | `decisions.jsonl: entry N: the final line has no line feed, so it was cut off while being written; delete it` and `3`; `Get-FileHash` on the log is the same before and after `check` | `Copy-Item "$backup\decisions.jsonl" $inputs` |
| With a publication built after at least one decision, change one letter inside the log's first entry | `decisions.jsonl: publication N was built from the log through entry M, which no longer matches; restore the log from the newest backup set`, once per publication, and `5` | `Copy-Item "$backup\decisions.jsonl" $inputs`, then `check` prints `No problems found.` |
| Move `gold.db` aside | Inputs checked as usual, no prefix check, and nothing created in `$stores` | Move it back |

Exit `5` wins over `3`: with both kinds of problem, every line is listed and
the command exits `5`.

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
