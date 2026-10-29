---
type: architecture
---
# Presentation Layer

## Purpose

Render household financial information for phone and desktop browsers.

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

## Initial Screens

- Current-month overview: income, expenses, savings, savings rate.
- Category view: current month and year-to-date spending.
- Account activity: balances and transfer activity.
- Trend view: month-over-month totals.

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
  months can still change (issue #12). Gold publishes the per-account, per-month
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
  ([`publications.md`](publications.md)). How the picker and banner look
  belongs to issue #109.
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
  `partial` total names the accounts that are not complete. How coverage is
  rendered belongs to issue #11.

## Non-Responsibilities

- Importing or editing raw bank data.
- Making categorization decisions.
- Using browser-stored financial data as a system of record.
