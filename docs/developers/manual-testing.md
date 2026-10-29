---
type: developers
---
# Testing by Hand

How to try each feature on your development profile,
`$env:APPDATA\budget\development.toml`. Its stores are derived and
scrappable. Commands are PowerShell, run from a checkout in one window, so the
variables from [Set up](#set-up) stay set.

Each feature has its own section. When a feature lands, add a section for it,
and when a pending feature reaches `main`, drop its marker.

## Set up

Close DB Browser for SQLite if it has a dev store open. Then:

```powershell
uv sync
$devProfile = "$env:APPDATA\budget\development.toml"
$env:BUDGET_PROFILE = $devProfile
$paths = uv run python -c "import json,sys,tomllib; print(json.dumps(tomllib.load(open(sys.argv[1],'rb'))['paths']))" $devProfile | ConvertFrom-Json
$stores = $paths.stores; $inputs = $paths.inputs; $exports = $paths.exports; $inbox = $paths.inbox
$ranges = "$env:LOCALAPPDATA\budget\dev-household\ranges.toml"
```

`inputs` must hold `accounts.toml`, `taxonomy.toml` and `rules.toml`.

Before a test that edits inputs or the profile, back them up, and copy them
back afterwards:

```powershell
$backup = "$env:LOCALAPPDATA\budget\manual-test-backup"
New-Item -ItemType Directory -Force $backup | Out-Null
Copy-Item $devProfile, "$inputs\taxonomy.toml", "$inputs\rules.toml", "$inputs\accounts.toml" $backup
```

### If an older profile fails

- **`migrate` fails with "no such table".** The store predates its stage's
  first schema. Delete `$stores\silver.db` or `$stores\gold.db` and migrate
  again; both are rebuilt from Bronze.
- **A decision log `main` refuses.** `main` refuses a log that holds a
  decision (exit 3). Empty it with
  `Set-Content "$inputs\decisions.jsonl" -Value '' -NoNewline`. A log without a
  final line feed would also join an appended line onto its last one.
- **No categories or rules.** Rules and decisions need at least one rule and
  two categories:

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
  Set-Content "$inputs\rules.toml" -Value @'
  format = 1

  [[rule]]
  id = "r-netto"
  when.description_contains = "NETTO"
  then.category = "groceries"
  '@
  ```

## Migrate

```powershell
uv run budget migrate
```

Exit 0. A store newer than the code is refused with exit 4: switch to the
branch that made it, or delete the derived store.

## Import

Put an export in `$inbox\<account_id>\`, then:

```powershell
uv run budget import --ranges $ranges
```

Expect `[1] <account>  stored` and a Silver line, and the file gone from the
inbox. With no fresh export from the bank, copy an archived one from
`$exports\<account_id>\` into the inbox: it is stored again as a repeat run and
adds no transaction. The README's [import outcomes](../../README.md#importing-the-inbox-budget-import)
list what each line means and each exit status.

## Rebuild Silver

```powershell
uv run budget rebuild --from silver
```

Expect a `Run <id>  <account>  accepted` line per import run, then the Silver
counts.

## Review

```powershell
uv run budget review
```

Lists open review items and quarantined runs; prints nothing when none are
open.

## Dashboard

Your dev profile needs `[dashboard]` and a passphrase
(`uv run budget set-passphrase`). Then `uv run budget serve`, open the
address it prints, and log in. Check the account picker, month picker and the
monthly overview against the current publication.

Without your profile, `uv run budget demo` serves synthetic data; the
README's [dashboard section](../../README.md#the-dashboard-budget-serve) has
the details.

## Gold publications (pending: #176)

These need the #176 stack. Run them in a worktree on its top branch, and
check that `rebuild` builds Gold there before you start:

```powershell
cd "$env:USERPROFILE\Documents\GitHub\budget"
git fetch origin claude/176-4-bronze-rebuild
git worktree add .claude\worktrees\176-try origin/claude/176-4-bronze-rebuild --detach
cd .claude\worktrees\176-try
uv sync
uv run budget migrate
```

| Test | Do | Expect |
| --- | --- | --- |
| First build | `uv run budget rebuild --from silver` | `Gold     published publication N` |
| Nothing changed | `uv run budget rebuild` | `the recipe is unchanged; nothing was published (publication N stays current)` |
| Same meaning | Change `"NETTO"` to `"netto"` in `rules.toml` or add a comment, then `rebuild` | Unchanged |
| Late-booking window | Add `[gold]` with `late_booking_days = 0` to the profile, then `rebuild` | A new publication |
| Decision | Append the classify line below, then `rebuild` | A new publication, the amount under Eating out |
| Retract | Append the retract line below, then `rebuild` | A new publication matching the one before the decision |
| Bad input | Append `this is not toml` to `taxonomy.toml`, then `rebuild --from silver` | Exit 3; restore the file and `rebuild` reports unchanged |
| Closed account | Set an account's `closed_on` before its latest transaction, then `rebuild` or `import` | Exit 3, naming the account; `import` leaves the inbox untouched |
| Import | Import as [above](#import) | Gold publishes for a new transaction, or reports unchanged for a repeat |
| Bronze rebuild | `uv run budget rebuild --from bronze` | Bronze, Silver and Gold lines; Gold unchanged |

The decision lines, for an empty log. The first picks the latest MENY
purchase:

```powershell
$id = uv run python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); p=c.execute('select max(publication_id) from publications').fetchone()[0]; print(c.execute(""select transaction_id from transactions where publication_id=? and description like 'MENY%' order by transaction_date desc limit 1"",(p,)).fetchone()[0])" "$stores\gold.db"
Add-Content "$inputs\decisions.jsonl" "{`"format`": 1, `"entry`": 1, `"decision_id`": `"d-0001`", `"recorded_at`": `"2026-10-27T18:00:00Z`", `"kind`": `"classify`", `"targets`": [`"$id`"], `"category`": `"eating-out`", `"reason`": `"dev test`", `"supersedes`": []}"
Add-Content "$inputs\decisions.jsonl" '{"format": 1, "entry": 2, "decision_id": "d-0002", "recorded_at": "2026-10-27T18:05:00Z", "kind": "retract", "targets": [], "reason": "dev test", "supersedes": ["d-0001"]}'
```

`max(publication_id)` is the current publication while there is no undo.

### Back to `main`

`main` refuses the stack's newer stores (exit 4) and a log holding a decision
(exit 3):

```powershell
Copy-Item "$backup\development.toml" $devProfile
Copy-Item "$backup\taxonomy.toml", "$backup\rules.toml", "$backup\accounts.toml" $inputs
Set-Content "$inputs\decisions.jsonl" -Value '' -NoNewline
Remove-Item "$stores\silver.db", "$stores\gold.db"
cd "$env:USERPROFILE\Documents\GitHub\budget"
git worktree remove --force .claude\worktrees\176-try   # "Invalid argument": a locked .venv exe; delete the folder after a restart
uv run budget migrate
uv run budget rebuild --from silver
```

Keep Bronze and `imports.jsonl` as they are: they record real runs.

## Clean up

```powershell
Remove-Item Env:BUDGET_PROFILE
Remove-Item $backup -Recurse
```
