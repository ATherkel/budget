---
type: architecture
---
# Presentation Layer

## Purpose

Render household financial information for phone and desktop browsers. The
dashboard is in Danish, supports keyboard use, and shows loading, empty,
unavailable and request-failure states.

## Boundary

Presentation consumes analytics reports only, as defined in
[`report-contract.md`](report-contract.md). It does not classify
transactions, calculate financial totals, or access source data. It never
reads Gold either: it names the publication in the report context, and
analytics opens it.

Presentation owns the interaction around a report: pinning the resolved
context on the page, keeping a response eligible only for the activity that
asked for it, restoring the selection on browser back and forward, and the
empty-selection prompt. The rules are in
[`report-contract.md`](report-contract.md#navigation-and-selection-transitions).

## Initial Technology Direction

- FastAPI for the HTTP application.
- Jinja templates and HTMX for server-rendered interactions.
- Plotly for charts where a chart improves comprehension.

This is a direction, not an implementation commitment; a technology change
must preserve the analytics-facing DTO boundary.

## Feature Modules

Each dashboard feature is a folder under `src/budget/dashboard/features/`
holding its view, its templates, its stylesheets and its own display helpers.
Its package exports a `Feature`: the folder, and a `register` function that
adds its routes to the `Dashboard` it is handed. `FEATURES` in
`budget.dashboard` lists the registered features one line each; a feature left
out is off. The overview shows the report and the pickers, so it needs `report`
and `view_state` registered too, and the report links each category to
`category` and its trust notes to `explanation`. The report needs `checks`
registered for its Kontrol tab. Every page sends a reader
who is not logged in to `login`, the page that logs in and out; the check
itself, the session cookie and the passphrase stay in `budget.dashboard`, so a
dashboard without `login` still refuses every page. `errors` explains why an
address is malformed or a page's figures cannot be shown: the overview, report
and category page need it registered to explain a failure, and a dashboard
without it answers a malformed address with FastAPI's own JSON. A feature that
serves no page of its own, such as `view_state` (the month, mode and account pickers), adds no routes: the pages that show
it include its templates. A feature's templates are named
`<folder>/<file>.html`, and `base.html` links every stylesheet in its folder,
so adding a feature with its own page edits no shared file. Helpers more than one feature uses live in the
`budget.dashboard.display` package, the pinned address every page links by
lives in `budget.dashboard.addresses`, reading the overview several pages show
lives in `budget.dashboard.reading`, and markup more than one page repeats is
a macro in `templates/_macros.html`. A template holds no chain of conditions:
wording that turns on several cases comes from a display helper. Moving the
existing pages into features is pending: [#569](https://github.com/ATherkel/budget/issues/569).

## Initial Screens

- Current-month overview: income, expenses, savings, savings rate.
- Category view: current month and year-to-date spending.
- Account activity: balances and transfer activity.
- Trend view: month-over-month totals.

## “Enkel” and “Avanceret”

“Enkel” is the calm monthly overview, with category investigation on demand.
“Avanceret” adds independently navigable **“Overblik”**, **“Detaljer”** (account
activity) and **“Kontrol”** (trust diagnostics and reconciliation). Mode is a
presentation preference available to every authenticated household reader.
Both summaries use the same [monthly report](report-contract.md#monthlyoverview);
changing mode never changes financial values or their trust semantics.

A fresh visit starts in “Enkel” and “Beløb”. Mode persists during the active visit,
not as a lasting preference. An explicit switch closes detail overlays and
returns to the destination mode's overview, preserving the shared report context
and “Beløb”/“Mod budget” choice. Once “Kontrol” ships, a targeted explanation
link opens it with a route back to the originating view. Browser back/forward
restores the recorded mode, tab and applicable detail/comparison state under the
[navigation contract](report-contract.md#navigation-and-selection-transitions).

The switch and advanced “Overblik”, “Detaljer” and “Kontrol” are available.
“Kontrol” answers whether each selected account's month can be trusted. It
opens with a table of accounts: a verdict, the start and end balances, both
[residuals](report-contract.md#diagnostics) and Evidence through (“Data til og
med”), each account linking to its “Detaljer”. The verdict is “Ingen fundne
forskelle” only for a fully covered month whose residuals are both zero, “Data
mangler” for partial Coverage, “Går ikke op” with the amount for a nonzero
residual and “Ukendt” for a missing balance; it never says the month adds up.
Under each account a waterfall walks from the start balance through each
component to the computed and the bank's end balance; a missing step leaves the
running total “Ukendt”. The page also shows Coverage, provisional reasons and
incomplete account-months, and says a zero difference does not prove the data
complete. Both modes retain access to the basic trust explanation.

## Data Trust Display

- Any report period that includes the current, still-accumulating calendar
  month always carries a visible provisional/month-to-date label at the point
  of display — not just a documented caveat, and with no exception. Which month
  is current is decided from today's date in Europe/Copenhagen;
  `transaction_date` itself is never converted. A household that is behind on
  its imports has *more* reason to see the label, not less, so no coverage
  status withholds it here.
- A period that is already closed carries the same label until, for every
  account in the report and *every month* in the period, one of the exports
  counted in the account's evidence ranges was produced at least the
  late-booking window (7 days unless the profile sets another) after
  that month ended *and* its range covers that month's last day. Late bookings
  land on their transaction date, so an export starting after a month cannot
  show them, however late it was produced. Checking every month, not only the
  period's last, keeps a year-to-date total provisional while one of its
  months can still change. Gold publishes the per-account, per-month
  half of this rule as `MonthlyBalanceSnapshot.late_bookings_settled`;
  analytics adds the current month and returns the label with the report.
  This bullet and the one above are the only statement of the rule; other
  documents cite them.
- Exactly one account is exempt from holding the label on a closed period: one
  that has never been imported, meaning its `GoldAccount.evidence_through` is
  null. It already reports `no_data` on its own line, and no export of it is
  outstanding, so it cannot be what the period is waiting for. The exemption is
  written on `evidence_through`, never on the period's coverage status: an
  account that *has* been imported reads `no_data` for any period its evidence
  does not reach, and a later export can still reach back and change that
  period — which is precisely what the label warns about.
- Known first-release limitation: an imported account with no booked
  transaction yet has no managed period, so no snapshot rows carry its flag
  and it cannot hold the label either. Its first booked transaction creates
  its rows, and reports restate.
- Every screen reads exactly one Gold publication, and all requests from one
  page read the same one. A screen showing any publication other than the
  current one carries a visible banner naming it (its label, and whether it is
  an as-was or as-known-at view). A past view takes the provisional label as
  of the publication's `known_at`, not today
  ([`publications.md`](publications.md)). How the picker and banner look is
  pending: [#109](https://github.com/ATherkel/budget/issues/109).
- A page opened on the current publication keeps reading it after a newer
  build becomes current, so its parts never mix two publications. That is a
  superseded page, not a past view: instead of the banner, it says that newer
  figures exist and offers a reload. When its result is no longer retained,
  the page offers the current publication explicitly and never substitutes it
  ([`report-contract.md`](report-contract.md#reportpublication)).
- Account and balance views must reflect each account's coverage status from
  analytics; a `partial` or `no_data` account must never render as if its
  balance or totals are complete.
- Every screen that shows a household-level measure (overview, category, and
  trend views) must display the coverage the report carries for it. A
  `partial` total names the accounts that are not complete.

## Non-Responsibilities

- Importing or editing raw bank data.
- Making categorization decisions.
- Using browser-stored financial data as a system of record.
