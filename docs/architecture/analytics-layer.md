# Analytics Layer

## Purpose

Produce reproducible reporting datasets from the Gold contract.

## Allowed Dependencies

- `GoldTransactionRepository`
- Gold contract fixtures
- Configuration for report date range and household presentation

## Forbidden Dependencies

- Bank APIs, connectors, CSV parsers, or import directories
- Bronze and Silver types, tables, repositories, or source identifiers
- Presentation templates and HTTP request objects

## Initial Measures

For a selected reporting period:

- **Income:** sum of `income` amounts.
- **Expenses:** absolute sum of `expense` amounts.
- **Net cash flow:** all included income plus expense amounts.
- **Savings:** income minus expenses; document later treatment of investments
  and debt repayment rather than assuming they are savings.
- **Savings rate:** `savings / income`, null when income is zero.
- **Category spending:** absolute expense total by `category_id`, net of any
  same-category `adjustment` amounts (refunds reduce the category they
  reverse rather than disappearing or counting as income).
- **Unclassified total:** sum of amounts on `unknown` transactions for the
  period, reported explicitly rather than silently excluded.

Transfers are excluded from all spending and income measures. Account activity
reports may include them separately.

## Coverage

For each account and reporting period, analytics derives a coverage status
from Gold's balance-chain evidence (`gold-contract.md` invariant 9):

- **`complete`**: every transaction in the period has a `balance` consistent
  with the chain, and the account was already under management before the
  period began.
- **`partial`**: the account has transactions in the period but the chain
  breaks, a `balance` is missing, or the account's data collection began
  partway through the period — a first, partial-month period is always
  `partial`, never `complete`.
- **`no_data`**: the account has no transactions in the period at all.

Coverage is tracked per account, not as one household-wide flag, so a report
can point at the specific account that needs attention. Reports must never let
missing or partial data read as a confirmed zero.

## Outputs

Analytics returns typed report DTOs or API-neutral dictionaries. It does not
persist report values as a new source of truth; results are recalculated from
Gold when requested or cached with explicit invalidation.
