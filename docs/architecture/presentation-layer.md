---
type: architecture
---
# Presentation Layer

## Purpose

The household dashboard, in Danish, for phone and desktop browsers. It
supports keyboard use and shows loading, empty, unavailable and
request-failure states.

## Boundary

Presentation reads analytics reports only
([`report-contract.md`](report-contract.md)). It never classifies, totals, or
reads source data or Gold: it names the publication in the report context and
analytics opens it. It owns the interaction around a report: pinning the
context, ignoring stale responses, back/forward restore and the
empty-selection prompt
([navigation contract](report-contract.md#navigation-and-selection-transitions)).

## Technology

FastAPI, Jinja templates with HTMX, and Plotly where a chart helps. A change
of technology keeps the analytics-facing DTO boundary.

## Feature Modules

Each feature is a folder under `src/budget/dashboard/features/` with its view,
templates (named `<folder>/<file>.html`), stylesheets and display helpers. Its
package exports a `Feature` whose `register` adds its routes. `FEATURES` in
`budget.dashboard` lists one feature per line; a feature left out is off.
`base.html` links every feature's stylesheets, so a new feature edits no
shared file. A feature without a page of its own, such as `view_state` (the
pickers), adds no routes; the pages that show it include its templates.

- The overview needs `report` and `view_state`. The report links to
  `category`, `explanation` and `checks` (“Kontrol”).
- `errors` explains malformed addresses and figures that cannot be shown.
  Without it, a malformed address gets FastAPI's JSON.
- `login` is the log-in page. The check itself stays in `budget.dashboard`, so
  a dashboard without `login` still refuses every page.

Shared helpers live in `budget.dashboard.display`, pinned addresses in
`budget.dashboard.addresses`, the shared overview read in
`budget.dashboard.reading`, and repeated markup as macros in
`templates/_macros.html`. A template holds no chain of conditions: wording
that depends on several cases comes from a display helper.

## “Enkel” and “Avanceret”

“Enkel” is the calm monthly overview, with category investigation on demand.
“Avanceret” adds the tabs “Overblik”, “Detaljer” (account activity) and
“Kontrol” (trust diagnostics). Every logged-in reader can switch. Both modes
use the same [monthly report](report-contract.md#monthlyoverview) and reach
the basic trust explanation, so mode never changes figures or trust.

A visit starts in “Enkel” and “Beløb”, and mode lasts for the visit only.
Switching mode closes overlays and opens that mode's overview, keeping the
report context and “Beløb”/“Mod budget”. An explanation link can open
“Kontrol” with a way back. Back and forward follow the
[navigation contract](report-contract.md#navigation-and-selection-transitions).

“Kontrol” shows the selected accounts' [diagnostics](report-contract.md#diagnostics):
Coverage per account, provisional reasons, incomplete account-months, Evidence
through, reconciliation with nonzero residuals first (each linking to
“Detaljer”), and Ukategoriseret, Reguleringer and Overførsler with Ind and Ud
apart, observed counts and Transfer pairing. Anything missing reads “Ukendt”.
The page says a zero difference does not prove the data complete, and that a
Transfer counts twice when both its accounts are selected.

## Data Trust Display

- **Provisional label.** A period that includes the current month always shows
  a provisional label where its figures are shown, whatever its coverage. The
  current month follows today's date in Europe/Copenhagen; `transaction_date`
  is never converted. A closed period keeps the label until, for every account
  and every month in it, a counted export was produced at least the
  late-booking window (7 days unless the profile sets another) after that
  month ended and covers its last day. Checking every month keeps a
  year-to-date total provisional while any of its months can change. Gold
  publishes the per-account-month half as
  `MonthlyBalanceSnapshot.late_bookings_settled`; analytics adds the current
  month. This bullet is the rule's only statement; other documents cite it.
- **Never-imported accounts.** On a closed period, an account whose
  `GoldAccount.evidence_through` is null cannot hold the label: it shows
  `no_data` and has no export outstanding. The exemption keys on
  `evidence_through`, never on coverage, because an imported account's
  `no_data` period can still change.
- **Limitation.** An imported account with no booked transaction has no
  snapshot rows, so it cannot hold the label until its first transaction
  restates the reports.
- **One publication per page.** Every request from a page reads the same Gold
  publication. A past view shows a banner with its label and whether it is
  as-was or as-known-at, and takes the provisional label as of its `known_at`
  ([`publications.md`](publications.md)). A page left on a superseded
  publication keeps reading it, says newer figures exist and offers a reload;
  once that result is gone, it offers the current publication and never swaps
  it in silently ([`report-contract.md`](report-contract.md#reportpublication)).
- **Coverage.** Account and balance views show each account's coverage, and a
  `partial` or `no_data` account never looks complete. Household measures
  (overview and category) show their coverage, and a `partial` total names the
  accounts that are not complete.

## Non-Responsibilities

- Importing or editing raw bank data.
- Making categorization decisions.
- Keeping financial data in the browser as a system of record.
