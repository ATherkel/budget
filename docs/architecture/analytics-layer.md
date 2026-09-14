# Analytics Layer

## Purpose

Produce reproducible reporting datasets from the Gold contract.

## Allowed Dependencies

- `GoldRepository` (accounts, categories, transactions, monthly balance
  snapshots)
- Gold contract fixtures
- Configuration for report date range and household presentation

## Forbidden Dependencies

- Bank APIs, connectors, CSV parsers, or import directories
- Bronze and Silver types, tables, repositories, or source identifiers
- Presentation templates and HTTP request objects
- `GoldLineageRepository`, which is reserved for review and audit tooling

## Initial Measures

For a selected reporting period:

- **Income:** sum of `income` amounts.
- **Expenses:** absolute sum of `expense` amounts, less `refund` amounts. A
  refund reduces spending, so category spending adds up to Expenses.
- **Net cash flow:** all included income plus expense and refund amounts.
- **Savings:** income minus expenses; document later treatment of investments
  and debt repayment rather than assuming they are savings.
- **Savings rate:** `savings / income`, null when income is zero.
- **Category spending:** absolute `expense` total by `category_id`, less
  same-category `refund` amounts (refunds reduce the category they reverse
  rather than disappearing or counting as income). Category-group spending
  sums its categories through `GoldCategory.group_id`.
- **Unclassified total:** sum of amounts on `unknown` transactions for the
  period, reported explicitly rather than silently excluded.
- **Account balance:** `closing_balance` from `MonthlyBalanceSnapshot`. A
  household balance for a month sums closing balances across accounts for
  that month only; balances are never summed across months.

Transfers and `adjustment` transactions are excluded from all spending and
income measures. Account activity reports may include them separately.

## Coverage

Gold publishes coverage for each account and reporting month on
`MonthlyBalanceSnapshot`. The rules are in [`gold-layer.md`](gold-layer.md)
and the meaning is in `CONTEXT.md`. Analytics reads coverage and never
recomputes it from balances.

A report spanning several accounts or months must show every contributing
account-month that is not `complete`; it may not summarize them away. A
requested month beyond the latest published month has no data. Coverage is
tracked per account, not as one household-wide flag, so a report can point at
the specific account that needs attention. Reports must never let missing or
partial data read as a confirmed zero.

## Outputs

Analytics returns typed report DTOs or API-neutral dictionaries. It does not
persist report values as a new source of truth; results are recalculated from
Gold when requested or cached with explicit invalidation.
