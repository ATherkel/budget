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
from Gold's balance evidence. Analytics evaluates the evidence; Gold only
carries it (`gold-contract.md` invariant 9).

A **link** joins two consecutive transactions on an account, in
`(booking_date, day_sequence)` order. It is **verified** when both carry a
`balance` and the later balance equals the earlier balance plus the later
amount; otherwise it is **broken**. A link spans the dates from the earlier
transaction's `booking_date` to the later one's. A period is judged by every
link whose span overlaps it, including the links into and out of the period,
so analytics also reads the period's `boundary_transactions`.

An account's evidence runs from its `coverage_start` to its
`evidence_through` (`GoldAccount`).

- **`complete`**: all of these hold:
  - `coverage_start` is before the period's first day;
  - `evidence_through` is on or after the period's last day;
  - every link whose span overlaps the period is verified.

  A period with no transactions that meets these conditions is `complete`
  with zero activity: the evidence shows that nothing happened.
- **`no_data`**: the account's evidence does not reach into the period at all,
  including an account with no imported data.
- **`partial`**: anything else. The evidence reaches into the period, but it
  starts or stops inside the period, or a broken link overlaps it. A break
  therefore makes every period its span overlaps `partial`, and an account's
  first period is always `partial`.

Every account returned by `list_accounts` gets a status for every reported
period; an account is never left out because it had no transactions. An
inactive account is reported only for periods its evidence reaches into.

Coverage is tracked per account, not as one household-wide flag, so a report
can point at the specific account that needs attention. Reports must never let
missing or partial data read as a confirmed zero.

## Outputs

Analytics returns typed report DTOs or API-neutral dictionaries. It does not
persist report values as a new source of truth; results are recalculated from
Gold when requested or cached with explicit invalidation.
