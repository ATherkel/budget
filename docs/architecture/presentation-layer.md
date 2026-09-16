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
  month must carry a visible provisional/month-to-date label at the point of
  display — not just a documented caveat. Which month is current is decided
  from today's date in Europe/Copenhagen; `transaction_date` itself is never
  converted. The label remains until every account in the report has an
  admitted export that was produced at least 7 days after the period ends *and*
  whose range covers the period's last day, because late bookings land on their
  transaction date: an export starting after the period cannot show them,
  however late it was produced. An account whose coverage for the period is
  `no_data` does not hold the label, since it already reports that it has
  nothing to say; the label exists for periods that may still change, not for
  accounts that were never imported.
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
