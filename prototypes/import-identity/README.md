# Reading the import-identity prototype

A guided tour of `identity-merge.prototype.html`. Open the file by double-clicking
it, then follow this page top to bottom. Every walkthrough uses made-up data.

This is **version 2**. Version 1 ran the rules exactly as PR #16 wrote them: all
17 of issue #5's scenarios passed, and all seven claims of the review
reproduced. The findings are the comment on PR #16. This version changes the
documents and makes the fixes the prototype's defaults, so each claim tab now
compares **PR #16 as written (left)** with **the fix (right)**.

## 1. What the thing in front of you is

The prototype is a toy version of the import rules in ADR-009 and ADR-010. You
feed it bank exports; it shows what the platform would end up storing and
reporting. Nothing is saved: reload and it is empty again.

It exists to answer one question:

> Do the rules give the same transactions and the same IDs no matter how the
> household happens to import its exports — and where do they break?

## 2. Six words you need

- **Export** — one CSV the bank makes for one account, covering a date range.
  Every row carries the account balance right after that row.
- **Import run** — one time you feed a file in.
- **Accepted / quarantined** — either the platform trusts the file and takes its
  rows, or it sets the whole file aside and uses nothing from it.
- **Transaction ID** — the fingerprint a transaction gets. Your future
  categories, notes and corrections hang off it, so it must never change.
- **Balance chain** — each row's balance should equal the previous balance plus
  this row's amount. That arithmetic is the proof that nothing is missing.
- **Coverage** (`complete` / `partial` / `no data`) and the **provisional**
  label — per account and month: is the month's data whole, and might it still
  change? A late-booked purchase lands on its purchase date, so a month that
  looks finished can still gain rows.

The two rules everything below tests:

1. **Identity.** A transaction is identified by account, date, amount, its text,
   and a counter *k* that separates genuinely repeated identical rows.
2. **Admission.** A newly imported export is accepted only if it still shows
   every transaction already known for the dates it covers, and its balances
   differ only by the rows it adds.

## 3. How to drive the page

- **Tabs** across the top. `Issue #5 baseline` replays the 17 scenarios from the
  ticket. `C1`–`C7` are the review's seven claims. `Free play` takes your own
  files. `Verdicts` is the summary.
- Each claim tab has **preset buttons**. A preset sets up a side-by-side
  comparison; in this version the left side is normally the rule as PR #16
  wrote it and the right side is the fix.
- **`Run all`** performs every import in order. `Next step` does one at a time,
  `Reset` starts over.
- The **yellow bar** lists what differs between left and right, and the same
  differences are highlighted yellow in both panels.
- Each panel then shows, top to bottom: the **import runs** (green = accepted,
  red = quarantined), **review items**, the **months × accounts grid** with the
  provisional row underneath, and the **admitted transactions**.
- The **Rule set** line at the top of each panel expands into every switch. It
  says *proposed rules* when nothing is changed from the new defaults, and names
  what is changed otherwise.

Start on `Issue #5 baseline` and check it says 17 of 17 pass. The ticket's
scenarios pass under the fixed rules as well as under the original ones; the
claim tabs are only worth reading once you trust that.

## 4. The seven claims, in the order that matters

### C1 Import order — the one most likely to bite you

**Do:** tab `C1`, press `Run all`.

**See:** left (file A then file B) has 25 transactions. Right (B then A) has 20,
and run A is red. The yellow bar says five transactions exist only on the left.
Both sides are PR #16 as written.

**Why it is a bother:** it is the same two files. Import them in the other order
and two weeks of February silently disappear, plus you get a review item asking
you to inspect data that is perfectly normal. Worse, the coverage grid says
`partial` for February either way, because February is the account's first
month — so nothing on the dashboard flags the loss.

**The cause:** runs were admitted in the order you happened to import them. The
older export A does not contain a purchase booked after A was made, so when A
arrives second it looks like A is hiding something.

**The fix:** admit exports in the order the *bank made* them. Press
`B→A: as written vs fixed` to see the same import order come out whole, and
`Fixed: A→B vs B→A` for the point of the exercise: no differences at all.
`silver-layer.md` now says `exported_on`, then `started_at`.

### C3 An export of old data gets today's date

**Do:** tab `C3`, preset `H alone: as written vs fixed`, `Run all`.

**See:** on the left, January, February and March 2026 are marked
`complete · zero`. The file only contains 2025. Because its filename says it was
produced on 15 April 2026, the platform concluded those months were proven
empty. On the right they read `no data`.

**Why it is a bother:** the dashboard would tell you that you spent nothing in
February, when really you never imported February. That is exactly the "missing
data must never read as a confirmed zero" rule, broken.

Press `C→H: as written vs fixed` for the other half: as written, importing the
history *after* a current export quarantines it and throws away all of 2025.
`Fixed: H→C vs C→H` shows the order no longer matters.

**The fix:** Bronze now records two dates. `exported_on` is when the bank made
the file (it is what the late-booking window counts from); `covers_through` is
the end of the range the operator asked for, declared at import, and it is what
coverage uses. Without a declaration it falls back to the export date, as before.

### C7 The provisional label lets go too early

**Do:** tab `C7`, preset `Missed late booking: as written vs fixed`, `Run all`.

**See:** left says March is `final`, right says `provisional`.

**Why it is a bother:** the rule was "wait 7 days after the month ends". The only
export dated after March starts on 1 April, so it cannot show a purchase dated
31 March that the bank booked on 2 April. March was declared settled on the
strength of a file that structurally cannot contain the thing we are waiting for.
(Coverage still marks March `partial`, so the data was not wrong — the label was.)

Two more in the same tab:

- `No-import account: as written vs fixed`. A registered account you never
  imported held *every* month provisional forever. It already reports `no_data`
  on its own line, so it no longer holds the label.
- `Quiet account: as written vs fixed`. Re-export an account that had no new
  activity and you get a byte-identical file, which Bronze records as a
  "repeat". As written that run contributed nothing — including its newer date —
  so a quiet account could never clear its label. A repeat now records its own
  export date. I hit this by accident: it made scenario 17 fail until I noticed,
  and one of your real exports ends 13 days before its export date, so the shape
  is real.

**The fix:** `presentation-layer.md` requires the qualifying export to cover the
period's last day and exempts `no_data` accounts; `bronze-layer.md` lets a
repeat run carry its dates.

### C4 A bad day locks the window forever

**Do:** tab `C4`, preset `As written vs the "accept discrepancy" decision`,
`Run all`.

**See:** on the left, export X is quarantined for a broken balance chain — fine,
that is the rule. But Z, a later and longer export covering the same dates, is
quarantined too. W, which starts after the bad date, is accepted. 1–10 March is
simply gone. The steps show the three manual decisions being tried: voiding
removes X but admits nothing; *same transaction* and *withdrawn* have nothing to
point at.

**Why it is a bother:** the bank recalculates the balances every time it makes an
export, so the only way the chain breaks is that the bank counts a row it never
exports — which it will keep doing. Every future export of that date breaks the
same way.

**The fix:** ADR-010 gains a fourth manual decision, *accept discrepancy*. The
right panel shows the result: Z accepted, three transactions recovered, and
March still honestly `partial`, because the chain really is broken. The break is
recorded, never repaired. (Preset `Persistent vs transient break` shows that
when only one file omitted a row, the next export was always fine — so this only
ever mattered for the persistent case.)

### C6 Fewer repeats: the two documents disagreed

**Do:** tab `C6`, preset `ADR-009 as written (admit) vs fixed (quarantine)`,
`Run all`.

The situation: two identical coffees on the same day, and a later export shows
only one. ADR-009 said raise a review item and keep the higher count, which
reads like "accept the file". Issue #5 scenario 7 said quarantine it.

**See:** left (admit) takes the file — but the coffee we insisted on keeping has
no place in that day's balances, so the chain breaks and March goes from
`complete` to `partial`. Right (quarantine) sets the file aside and raises the
review item.

**Then press** `Fixed: quarantine, then a withdrawn decision`: recording "the
bank withdrew it" admits the file cleanly, with the chain intact and April
imported.

**The fix:** ADR-009 keeps the quarantine and now says a *withdrawn* decision
settles it. It also states that the missing repeat's amount counts as an
explained balance difference, so the date does not also raise an
export-disagreement item.

### C2 Two documents defined the ID differently

**Do:** tab `C2`, preset `A→B: transaction.md fingerprint vs ADR-009`,
`Run all`, then look at the **ID over steps** column on both sides.

**See:** on the right (ADR-009) every row says `stable`. On the left, 6 of 15 IDs
change when the second export is imported. The yellow bar deliberately does not
count ID differences here: two schemes always produce different IDs, and the
question is whether an ID *moves*.

**Why it is a bother:** `docs/domains/transaction.md` defined identity as a
fingerprint including the row's *position in the file*. Positions move between
exports, so the ID of a transaction you already categorised changes when a newer
export arrives, and your decision detaches from it. Preset
`Late booking: balance-anchored vs ADR-009` shows the same damage from putting
the balance in the ID — which is precisely why ADR-009 rejected it.

**The fix:** `transaction.md` now points at ADR-009 instead of defining its own
rule. Note the preset `Fingerprint, as-written order: A→B vs B→A`: C1's fix
already removes the import-order half of the problem, but only the identity rule
stops the IDs moving mid-import.

### C5 Three unwritten details of the identity

**Do:** tab `C5`, try each of the three presets. Left is the unlucky reading,
right is what ADR-009 now says.

Each is a detail ADR-009 did not spell out: whether `-45,0` and `-45,00` are the
same amount, whether a non-breaking space counts as whitespace, and what
"visibly identical" means when counting repeats. The third is the ugly one — the
left-hand transactions table shows a red **ID collision**: two different
transactions sharing one ID.

**Why it is a bother:** none of these bite your current files (they always use
two decimals and contain no non-breaking spaces), so this is insurance. But one
of your real exports has 176 rows with double spaces inside the text, so the
whitespace rule is already load-bearing.

**The fix:** ADR-009 now states all three: the amount is quantized to hundredths,
whitespace means any Unicode whitespace including 0xA0, and *k* counts identity
text.

## 5. What changed in the documents

| File | Change | Claim |
| --- | --- | --- |
| `docs/architecture/silver-layer.md` | Admit runs in `exported_on` order, then `started_at`; fewer repeats quarantine and a *withdrawn* decision clears them; balances compared only where both state one | C1, C6 |
| `docs/architecture/bronze-layer.md` | `covers_through` and `repeat_of` on `ImportRun`; the filename date is the production date; a repeat records its own dates | C3, C7 |
| `docs/architecture/presentation-layer.md` | The qualifying export must cover the period's last day; `no_data` accounts do not hold the provisional label | C7 |
| `docs/decisions/ADR-009-transaction-identity.md` | Amount, whitespace and *k* spelled out; export-date admission order; fewer-repeats rule and its way out; two new rejected options | C1, C5, C6 |
| `docs/decisions/ADR-010-quarantine-inconsistent-exports.md` | The *accept discrepancy* manual decision | C4 |
| `docs/decisions/ADR-006-balance-chain-reconciliation.md`, `docs/architecture/gold-contract.md` | `evidence_through` derives from `covers_through` | C3 |
| `docs/domains/transaction.md` | Points at ADR-009 instead of defining a competing fingerprint | C2 |
| `CONTEXT.md` | *Covers through* and *Export date* as separate terms | C3 |
| `docs/agents/bronze-agent.md`, `docs/agents/silver-agent.md` | Acceptance criteria follow the above | C1, C3, C4, C6 |

## 6. Trying your own files

`Free play` takes a CSV through the file picker, asks which account it belongs to
(the export date if the filename has no `-YYYYMMDD` suffix, and optionally the
range end), and then shows the same panels. Tick *compare with a second rule set*
to run your own imports under two rule sets at once. Small cut-down versions of
your real exports are in `imports\mwe\` (gitignored, never committed): `c1-*`
through `c7-*` match the claim tabs, `s10-*`/`s12-*` are the broken-file cases.
They behave exactly like the synthetic walkthroughs under both rule sets, which
is the evidence that none of this is an artefact of made-up data.
