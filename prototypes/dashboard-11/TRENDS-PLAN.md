# Final design exploration: budget and category trends

28 September 2026. Astra coordinates and reviews; native V4.1 Flash implements.
Continue the established throwaway prototype and its recorded verification
exception. Do not promote prototype code into production.

User requests Mod budget in Enkel, a Budgetteret trend, and category-filtered
trends. Subcategories are deferred; no evidence yet warrants the extra control.
Recommendation: finish this bounded exploration, get household feedback, then
use the design and accepted report contracts as the production implementation
reference. This recommendation has not yet been accepted by the user.

## Acceptance contract

- Enkel exposes Beløb / Mod budget, including elapsed-month markers. Keep the
  default simple overview and quiet incompleteness note. Mode changes preserve
  financial selection. Reserve arithmetic and savings reconciliation stay in
  Advanced or on-demand detail; do not paste the full advanced budget panel into
  the simple overview. Category transactions remain accessible.
- Advanced Udvikling over tid retains its periods and adds a labelled category
  selector with Alle kategorier and existing category names across the selected
  publication's reports, not only the current month's active categories.
  The all-category view retains the existing series plus Budgetteret; choosing
  a category shows only its actual expenses and monthly expense budget.
- Use frozen fixture amounts: actual category net spending; ordinary budget row
  allocated; overall plannedSpending. Never use accumulated available reserves
  as expected monthly expenses. Existing Ferie earmarking is savings, not an
  expense forecast: explain its exclusion concisely, and show no expense budget
  for it unless the fixture has a genuine expense plan. No new invented budget
  engine or accounting model. A full monthly budget is not prorated by today.
- Budget points only exist for the budget's matching publication/account scope
  and explicit months. Unavailable budget is unknown, never zero or extrapolated.
  Preserve missing actual data as gaps. Confirmed complete category absence may
  be zero; partial missing category must remain unknown. Keep negative refunds.
- Legends, accessible chart title/description, point labels, and exact-value
  table reflect chosen category and distinguish budget from provisional actual
  figures. Budget styling must not share the provisional-only visual convention.
- Category/period/account/publication changes compose correctly; invalid category
  selections reset visibly to all categories. No stale totals or exceptions.
- Retain Danish UI, synthetic fixtures, loopback-only server, checks separation,
  publication banners, month markers, and all existing valid navigation.

## Scope and evidence

Worker owns prototypes/dashboard-11 except TRENDS-PLAN.md, CHECKPOINT.md, and
ISSUE-11-*.md. No configuration/dependency/production changes, GitHub writes,
commits or pushes. Existing six Ruff findings are not approved for suppression.
Baseline: %TEMP%/budget-dashboard-11-before-trends-20260928/dashboard-11;
all prototype files are already untracked, so HEAD is not a useful patch baseline.

Verify JavaScript syntax, fixture auditor, independent known budget/category
values, unavailable scope/month behavior, actual browser interaction at desktop
and phone widths, no overflow/errors. Use CUA for browser QA. If it is unavailable,
record the limitation and let Astra perform the missing UI checks; no external
CDP workaround. If Python changes, run the locked quality tools and document the
pre-existing Ruff exceptions separately. Update README/HANDOFF/SESSION without
erasing history; report exact changed files/evidence in TRENDS-IMPLEMENTATION.md.

Routing: doctor static-ready on DeepSeek API, native astra_flash_builder role;
global default is Terra but this task's latest turn_context confirms gpt-6-astra.
Runtime provider inference metadata remains unverified; no paid probe.

## Production scope decision received during this pass

The maintainer explicitly approved including read-only budget comparison in the
first usable release. Targets will be maintained outside the dashboard; budget
editing and forecasting are deferred. This changes the earlier #2 exclusion for
this bounded capability, not the other exclusions. The production budget input
and versioning contract still needs agreement before implementation. Prototype
carry-forward and earmarking behavior is design evidence, not an accepted engine.
