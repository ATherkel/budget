# Analytics Layer

## Purpose

Produce reproducible reporting datasets from the Gold contract.

## Allowed Dependencies

- `GoldRepository` (accounts, categories, transactions, category allocations,
  monthly balance snapshots)
- Gold contract fixtures
- Configuration for report date range and household presentation

## Forbidden Dependencies

- Bank APIs, connectors, CSV parsers, or import directories
- Bronze and Silver types, tables, repositories, or source identifiers
- Presentation templates and HTTP request objects
- `GoldLineageRepository`, which is reserved for review and audit tooling

## Initial Measures

For a selected reporting period, a `refund` nets into the measure of its
category's `GoldCategory.direction`. Every sum below uses signed `amount`s.

- **Income:** Σ `income` + Σ refunds with direction `income`.
- **Expenses:** −(Σ `expense` + Σ refunds with direction `expense`). A
  refunded purchase therefore reduces Expenses as well as its category.
- **Net cash flow:** Income − Expenses.
- **Savings:** Income − Expenses, equal to net cash flow in this release;
  document later treatment of investments and debt repayment rather than
  assuming they are savings.
- **Savings rate:** `savings / income`, null when income is not positive.
- **Category spending:** summed over category allocations, not transactions:
  for each expense-direction category, −(Σ allocations of `expense`
  transactions + Σ allocations of refunds) in that category. When refunds
  exceed purchases in the period, the category shows negative spending (a net
  refund). It is reported signed:
  never clamped to zero and never moved to the purchase's period. Category
  spending therefore always adds up to Expenses. Styling belongs to issue #11.
- **Unclassified:** for `unknown` transactions, money in (Σ positive amounts),
  money out (Σ negative amounts), and a count.
- **Uncategorized adjustments:** the same three figures for `adjustment`
  transactions, which never carry an allocation.

Money in and out are never netted against each other on these last two lines,
and neither line counts toward Income or Expenses. Every transaction in the
period is counted in exactly one of: Income/Expenses, transfers, Unclassified,
or Uncategorized adjustments.

Category-group spending sums allocations through `GoldCategory.group_id`.
Because a transaction's allocations sum exactly to its amount, category
spending still adds up to Expenses — and keeps adding up once a transaction
carries more than one allocation. Analytics must never mix the two facts in one
sum: a transaction and its allocations are the same money.
Account balance is the snapshot's `closing_balance`, summed across accounts
for one month only; balances are never summed across months.

Transfers are excluded from all spending and income measures. Account activity
reports may include them separately.

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

Every household-level measure carries combined coverage: `complete` only
when every contributing account-month is complete, `no_data` when none has
evidence, and `partial` otherwise. A partial measure names its incomplete
accounts. An account without transactions still contributes a coverage status.

## Outputs

Analytics returns typed report DTOs or API-neutral dictionaries. It does not
persist report values as a new source of truth; results are recalculated from
Gold when requested or cached with explicit invalidation.
