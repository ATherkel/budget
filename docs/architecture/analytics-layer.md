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
- **Category spending:** absolute expense total by `category_id`.

Transfers are excluded from all spending and income measures. Account activity
reports may include them separately.

## Outputs

Analytics returns typed report DTOs or API-neutral dictionaries. It does not
persist report values as a new source of truth; results are recalculated from
Gold when requested or cached with explicit invalidation.
