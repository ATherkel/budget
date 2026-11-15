---
type: developers
---
# Example Walkthroughs

A walkthrough is a script under `examples/` that runs real commands on
synthetic data and prints what they print. A test compares each transcript
below with the script's output, so the transcript cannot drift.

## Silver walkthrough

`examples/silver_walkthrough.py` runs the whole story on synthetic data in one
temporary folder, with no input from you. It writes a development profile and
a `joint-current` account, saves a March export in `inbox\joint-current\`,
runs `budget import` and `budget review`, then does the same with an April
export whose balance chain breaks. The profile, inbox, ranges files, stores,
archive, import log and routine log all stay in that folder, and nothing
outside it is read or written. Run it with:

```powershell
uv run python examples/silver_walkthrough.py
```

Each import declares its range in a ranges file
([the monthly import](../architecture/operations.md#w1-the-monthly-import)) beside the profile, so nothing asks at the
prompt. March's `ranges-march.toml` is:

```toml
format = 1

[default]
from = 2026-03-01
through = 2026-03-05
```

Each command line ends with its exit status after `->`, and the lines indented
under it are what the command printed. A line starting with `#` is the
script's own note, not command output. Every identifier the commands print is
real. The script replaces each run of 16 or more lowercase hexadecimal
characters with `<id>`, so this transcript is reproducible:

```text
budget migrate -> 0
budget import --ranges ranges-march.toml -> 0
  [1] joint-current  stored
  Silver   1 admitted, 0 quarantined, 0 dropped
  Gold     published publication 1 (cause build)
  Changes  no previous publication to compare; publication 1 is current.
  Published figures: publication 1 (current)
  joint-current  2026-03  partial  provisional: late bookings unsettled
  joint-current  2026-04  no data  provisional: current month, late bookings unsettled
  Unclassified money, by account and month
    joint-current  2026-03  in 0.00 DKK, out -45.00 DKK, 1 transaction
    joint-current  2026-04  unavailable: no data
  Open review items
    Silver (operational): none
    Gold (publication 1): unclassified 1
  Import evidence (operational, apart from published figures)
  joint-current  latest export 2026-03-06  evidence through 2026-03-05
    quarantined  none
budget review -> 0
  <id>  unclassified  gold  publication 1  targets 641b439a
    target 641b439a  joint-current  2026-03-01  -45.00 DKK  "NETTO"  bank category Mad
    settle  choose a rule or classify a target as a category or adjustment
budget import --ranges ranges-april.toml -> 0
  [1] joint-current  stored; Silver quarantined it: balance-break, balance-chain-break
  Silver   1 admitted, 1 quarantined, 0 dropped
  Gold     published publication 2 (cause build)
  Review  1 balance-break opened
  Published figures: publication 2 (current)
  joint-current  2026-03  partial  provisional: late bookings unsettled
  joint-current  2026-04  no data  provisional: current month, late bookings unsettled
  Unclassified money, by account and month
    joint-current  2026-03  in 0.00 DKK, out -45.00 DKK, 1 transaction
    joint-current  2026-04  unavailable: no data
  Open review items
    Silver (operational): balance-break 1
    Gold (publication 2): unclassified 1
  Import evidence (operational, apart from published figures)
  joint-current  latest export 2026-03-06  evidence through 2026-03-05
    quarantined  <id>  2026-04-01..2026-04-02  balance-chain-break
budget review -> 0
  <id>  balance-break  joint-current  2026-04-02..2026-04-02  run <id>  payload <id>
  <id>  unclassified  gold  publication 2  targets 641b439a
    target 641b439a  joint-current  2026-03-01  -45.00 DKK  "NETTO"  bank category Mad
    settle  choose a rule or classify a target as a category or adjustment
```

Each import rebuilds Silver from everything Bronze holds and publishes Gold
from it, so the walkthrough runs no `budget rebuild` of its own. It writes a
small `taxonomy.toml` and an empty `rules.toml` beside `accounts.toml`,
because Gold needs both. With no rules the
transaction stays unclassified, so `budget review` lists Gold's `unclassified`
item beside Silver's. The profile is a
development one, so no backup set follows; in production the summary would
end `Backup   backup set <name> written`. The April import exits 0 even though
Silver quarantines its run: a quarantine is a result, not a failure, and the
file was stored, archived and removed from the inbox. `budget review` prints
nothing when no item is open, and exits 0.
