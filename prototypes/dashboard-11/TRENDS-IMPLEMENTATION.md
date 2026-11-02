# Third prototype round: budget and category trends

**Astra acceptance, 28 September:** functional implementation accepted following
the correction recorded below. The remaining browser checks are now complete:
desktop 1280 has no document overflow, historical publications show no current
budget, custom/invalid ranges and YTD recovery work, and the corrected zero
labels and exclusion note were verified after reloading. No console warnings or
errors were reported. Phone 390/320 evidence is recorded below. The six existing
Ruff findings remain open; this is not a fully clean quality-gate declaration.
No household usability trial is claimed. Latest resumable state: CHECKPOINT.md.

28 September 2026. Implementation report for the bounded exploration in
[TRENDS-PLAN.md](TRENDS-PLAN.md). Throwaway prototype work: nothing here is
promoted, and no participant has used this version.

🤖 Added by Codex (deepseek/deepseek-v4.1-flash route; the host did not expose
model metadata to this worker, so the routing is unverified here)

## What now exists in the screen

- **Enkel exposes Beløb / Mod budget.** The everyday view keeps the three plain
  figures, the coverage line, the quiet incompleteness note and the category
  list, and its spending panel now carries the same `Beløb` / `Mod budget`
  toggle that Advanced always had. `Mod budget` shows one row per ordinary
  expense category with the used amount, the amount available, the remainder
  and, in the running month, the elapsed-time marker. The marker is calendar
  position only (15 of 30 days, 50 %, 15 September 2026) and is never drawn for
  a closed month or a reserve row.
- **The reserve and the savings reconciliation stay out of Enkel.** The simple
  budget view lists only ordinary monthly expense plans and closes with one
  line: Ferie is earmarked saving rather than a monthly expense budget, so it is
  not listed, and saved vacation remainders are not expected spending.
  `Avanceret` keeps the earlier carry-forward row and the
  `Opsparing efter øremærkning` block unchanged. Tapping any category, in either
  mode, still opens the on-demand detail with its transactions and arithmetic.
- **Advanced `Udvikling over tid` has a labelled category selector.** Options are
  `Alle kategorier` plus every category the selected accounts show anywhere in
  the selected publication's reports, so a category that only appears in an
  older month is still offered. The periods and the existing three series are
  unchanged.
- **`Alle kategorier` adds a `Budgetteret` series** built from the fixture's
  overall `plannedSpending` (18.300,00 kr. per budget month).
- **A chosen category shows only that category**: its actual net spending
  (purchases minus refunds) and its own monthly expense plan from the budget
  row's `allocated` field.
- **Budget points exist only where the budget applies.** The synthetic budget
  belongs to one publication, both example accounts and the explicit months
  July, August and September 2026. April, May and June therefore carry no budget
  point, and a single-account selection or a past publication has no budget at
  all. In that case the series is dropped and a quiet note says the budget is
  unknown for this view rather than zero.
- **Missing is not zero.** A calendar month without a report stays a gap. A
  category with no rows in a month whose accounts are all complete reads
  `0,00 kr.` and is labelled *Ingen kategoriserede udgifter* together with that
  month's own status label and coverage label; the same absence in a partial
  month stays `Ukendt`. August's net refund keeps its negative sign
  (−600,00 kr. for `Tøj og sko`).
- **Budget styling does not borrow the provisional convention.** Provisional or
  incomplete actuals keep the dashed line and hollow circle; budget figures use a
  solid line, filled square points and their own colour (`#6f57a8`), and the
  legend's `(plan)` marker says the same.
- **Labels and the table follow the choice.** The chart title and description name
  the chosen category, say whether budget figures exist in this view, and state
  that a gap is not a zero; every point carries an accessible label. The
  exact-value table has one column per drawn series, marks budget cells, and adds
  *ingen kategoriserede udgifter* where a zero came from a categorised absence
  rather than from a missing month. The chart footnote names the groups the key
  figures leave out: amounts without a category and internal transfers.
- **Selections compose.** Changing period, account selection or publication
  re-renders the trend; a category that no longer exists in the new view resets
  visibly to `Alle kategorier` with a short status note. Switching between Enkel
  and Avanceret keeps the accounts, month, publication and now also the
  `Beløb` / `Mod budget` choice.

## Frozen inputs

No fixture change was made. `example.json` is byte-identical to the pre-round
baseline snapshot (SHA-256 `060F4337441332D8812E4FD26134E4803E402881C3F53CC14BEC09BFB8A7F2C9`
for both copies). The trend reads only existing frozen fields: category
`netSpending`, budget row `allocated`, budget block `plannedSpending`, and the
reserve row's `carryForward` / `categoryId` flags that keep Ferie out of the
expense plan. Nothing is prorated by today's date and no new budget arithmetic
was invented.

## Changed files

| File | Change |
| --- | --- |
| `prototypes/dashboard-11/app.js` | Category state and reset; `categoryUniverse()`, `trendBudget()`, `trendBudgetBlock()`, `trendSeries()`, `trendValue()`, `trendPointLabel()`; rewritten `trendPanel()`; simple-mode budget variant; `simpleView()` uses the spending switch; `render()` reset check; `setMode()` no longer forces `Beløb`; new `#trend-category` change handler |
| `prototypes/dashboard-11/style.css` | Numeric table cells marked by class instead of column position; budget swatch, budget cell background and `.trend-reset` note; category select width |
| `prototypes/dashboard-11/check_fixtures.py` | Hand-checked trend constants and `audit_trend_categories` / `audit_trend_budget` / `audit_trend_contract`, wired into `main()` |
| `prototypes/dashboard-11/README.md` | New English section for this round; history kept |
| `prototypes/dashboard-11/HANDOFF.md` | New status section for this round; history kept |
| `prototypes/dashboard-11/SESSION.md` | New agent-check appendix; history kept |
| `prototypes/dashboard-11/TRENDS-IMPLEMENTATION.md` | This report |

Untouched by this worker: `TRENDS-PLAN.md`, `CHECKPOINT.md`, `ISSUE-11-*.md`,
`ISSUE-2-BUDGET-SCOPE.md`, `example.json`, `build_example.py`, `serve.py`,
`index.html`, and every path outside `prototypes/dashboard-11/`. No configuration,
dependency, GitHub, commit or push action was taken.

## Verification performed

Run from `C:/Users/Therkel/.codex/worktrees/641b/budget`:

| Command | Result |
| --- | --- |
| `node --check prototypes/dashboard-11/app.js` | exit 0, no syntax error |
| `py -3.12 prototypes/dashboard-11/check_fixtures.py` | exit 0, `OK: 3 offentliggørelser og 2272 kontroller uden fejl.` |
| baseline `check_fixtures.py` from `%TEMP%/budget-dashboard-11-before-trends-20260928/dashboard-11` | exit 0, 2236 checks; this round adds 36 trend checks |
| in-memory negative control: set August `clothes` `netSpending` to `0.00`, then run `audit_trend_contract` | 1 failure, naming the August category set; the new audit detects drift instead of passing vacuously |
| `uv run ruff check .` | exit 1, exactly the six pre-existing findings (INP001 + CPY001 on `build_example.py`, `check_fixtures.py`, `serve.py`); no new finding, none suppressed (`LINT-PROPOSAL.md` still awaits the owner) |
| `uv run ruff format --check .` | exit 0, `75 files already formatted` |
| `uv run ty check` | exit 0, `All checks passed!` |
| `uv run complexipy` | exit 0, all functions within 15 (new: `audit_trend_contract` 2, `household_reports` 3, `audit_trend_categories` 7, `audit_trend_budget` 11) |

The uv commands ran with `UV_CACHE_DIR=%TEMP%\budget-uv-cache` and
`UV_TOOL_DIR=%TEMP%\budget-uv-tools`, because the sandbox cannot write
`%LOCALAPPDATA%\uv`; the locked versions resolved offline (ruff 0.16.8). uv also
created a local `.venv` for that run, which `git status` does not report.

## Review correction (28 September 2026)

One consolidated review correction, `app.js` only:

- Restored the chart footnote that says amounts without a category are excluded:
  *Beløb uden kategori og interne overførsler er ikke med i nøgletallene.*
- Qualified the zero wording. A zero point now reads *Ingen kategoriserede
  udgifter* followed by the month's status label and coverage label, exactly like
  the other actual points, because a fully covered month can still be provisional
  or carry uncategorised money. The table cell says *ingen kategoriserede
  udgifter*. The numeric rule is unchanged: a zero is still drawn only when the
  month's accounts are complete.
- The stale comment `budget experiment (Advanced only)` now reads
  `budget comparison (Enkel and Avanceret)`.

Targeted check after the correction: `node --check prototypes/dashboard-11/app.js`
→ exit 0. No whole-suite rerun was requested or performed; every earlier result
in this report stands, and this correction touched no fixture, audit script or
stylesheet.

## Browser verification is outstanding

This worker could not complete the interactive checks. The browser tool was
available early in the session (it opened <http://localhost:8011> in the Codex
In-app Browser and rendered the Danish login screen), but during the QA pass
`cua.getState()` returned `{"apps":[],"browsers":[]}`, and a repeat
`cua.getState()` plus `cua.listBrowsers({emit:false})` also returned an empty
list. No alternative browser runtime and no CDP workaround were used, per the
brief.

Root's browser pass has since run, and reported these results:

- Enkel in `Mod budget`: the elapsed-month marker is drawn, and no savings panel
  appears.
- `Boligudstyr og møbler`: 8.700,00 kr. in August and 1.900,00 kr. in September,
  against its 1.500,00 kr. monthly plan.
- A category with no rows: `Ukendt` in April (a partial month), `0,00 kr.` from
  May to July.
- `Tøj og sko`: −600,00 kr. in August, the net refund kept negative.
- A single-account selection: the quiet "no budget in this view" note.
- Changing to an account selection that has no such category: the visible reset
  note.
- 390 and 320 pixel widths: no horizontal overflow.

Root continues the remaining checks. Not verified by anyone yet, and not claimed
here: the 1280×900 desktop pass, the remaining trend controls (category
switching, budget and provisional styling, the exact-value table) and a render
check of the corrected zero wording above.

## Decisions that need root's review

These are the judgement calls the accepted contract left to the implementer:

1. **Enkel's budget list omits the reserve row.** The contract says to show no
   expense budget for Ferie, and the simple view is meant to stay quiet, so only
   ordinary expense plans are listed and one line explains the exclusion.
   Advanced keeps the earlier carry-forward row and the savings reconciliation.
2. **The mode switch preserves `Beløb` / `Mod budget`.** Read as part of
   "mode changes preserve financial selection"; the earlier forced reset to
   `Beløb` was removed.
3. **The category list is the union for the selected accounts.** A category that
   exists only for accounts outside the current selection is not offered, so
   changing the account selection can reset the choice - visibly, with a status
   note.
4. **An unavailable budget removes the series** rather than drawing an empty one,
   and the panel says the budget is unknown for this view.
5. **Budget colour and marker:** solid line, filled square, `#6f57a8`.

## Tracking

The new measure-classification request - splitting fixed from other expenses and
showing a monthly `rådighedsbeløb` - is issue
[#99](https://github.com/ATherkel/budget/issues/99), raised in
[this #11 comment](https://github.com/ATherkel/budget/issues/11#issuecomment-5865951679).
It is not implemented in this bundle and was not part of the review correction.

## Limits

- No browser interaction evidence was produced by this worker in this round (see
  above); root's own pass covers part of it, and the 1280×900 desktop check is
  still open.
- The new Python audit checks the fixture's trend-relevant figures and the
  missing-versus-zero rule, not the JavaScript. The JavaScript change is covered
  by `node --check` and by reading the code.
- The six pre-existing Ruff findings are unchanged and remain unsuppressed.
- No participant has seen this version; #11 stays open.
