# Presentation Layer

## Purpose

Render household financial information for phone and desktop browsers.

## Boundary

Presentation consumes analytics report DTOs only. It does not classify
transactions, calculate financial totals, or access source data.

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
- A period that is already closed carries the same label until every account in
  the report has an admitted export that was produced at least 7 days after the
  period ends *and* whose range covers the period's last day, because late
  bookings land on their transaction date: an export starting after the period
  cannot show them, however late it was produced.
- Exactly one account is exempt from holding the label on a closed period: one
  that has never been imported, meaning its `GoldAccount.evidence_through` is
  null. It already reports `no_data` on its own line, and no export of it is
  outstanding, so it cannot be what the period is waiting for. The exemption is
  written on `evidence_through`, never on the period's coverage status: an
  account that *has* been imported reads `no_data` for any period its evidence
  does not reach, and a later export can still reach back and change that
  period — which is precisely what the label warns about.
- Every screen reads exactly one Gold publication, and all requests from one
  page read the same one. A screen showing any publication other than the
  current one carries a visible banner naming it (its label, and whether it is
  an as-was or as-known-at view). A past view takes the provisional label as
  of the publication's `known_at`, not today
  ([`publications.md`](publications.md)). How the picker and banner look
  belongs to issue #11.
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
