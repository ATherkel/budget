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
  display — not just a documented caveat.
- Account and balance views must reflect each account's coverage status from
  analytics; a `partial` or `no_data` account must never render as if its
  balance or totals are complete.

## Non-Responsibilities

- Importing or editing raw bank data.
- Making categorization decisions.
- Using browser-stored financial data as a system of record.
