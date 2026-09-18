# Gold Layer

## Purpose

Represent household financial facts as a small dimensional model. Gold stays
stable when source systems change.

The normative field list, invariants, and interfaces are in the
[Gold contract](gold-contract.md). This document explains the model behind
them: business processes, grains, dimensions, and the balance-chain and
coverage rules. Field names here are illustrative references to that
contract. See [ADR-007](../decisions/ADR-007-dimensional-gold-model.md) and
[ADR-008](../decisions/ADR-008-category-allocation-grain.md).

## Responsibilities

- Publish the account and category dimensions from the household registries.
- Materialize one Gold transaction per booked Silver transaction, classify it
  (rules and overrides: issue #7), and publish its category allocation.
- Evaluate each account's balance chain and publish a balance check per
  transaction.
- Publish a monthly balance snapshot with coverage for every month of each
  account's managed period.
- Keep lineage behind the privileged lineage interface.

## Business Processes and Grains

| Process | Fact | Grain |
| --- | --- | --- |
| Booking money movements on an account | `GoldTransaction` | One booked transaction on one account. |
| Assigning a transaction to a category | `GoldCategoryAllocation` | One category allocation of one booked transaction. Exactly one per classified transaction in the first release. |
| Observing account balances | `MonthlyBalanceSnapshot` | One account for one reporting month of its managed period, including months with no transactions. |

Category assignment is a process of its own because it is the household's
judgement about a transaction, not a property of the money movement, and
because one movement can legitimately belong to more than one category. Giving
it its own grain now means the day a mixed purchase is divided by hand, nothing
about the transaction fact or any consumer query changes
([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).

Budgets and forecasts are out of scope for the first release. They appear in
the bus matrix only to check that the dimensions will conform later.

## Bus Matrix

| Process | Date | Account | Category |
| --- | --- | --- | --- |
| Booked transactions | ✓ (transaction date) | ✓ | — |
| Category allocations | ✓ (transaction date) | ✓ | ✓ |
| Monthly balance snapshots | ✓ (month) | ✓ | — |
| *Future: budget targets* | ✓ (month) | — | ✓ |

Currency is an attribute of the account, not a separate dimension, because
every amount is in its account's currency. A future budget should be
compared with actuals only after both are aggregated to category × month.
Joining a monthly budget directly to transactions would count the budget once
per transaction.

## Dimensions

- **Account.** Only accounts inside the reporting boundary
  (`ownership_scope` of `household` or `person`). First-release types are
  `current` and `savings`. There is no person dimension and no account
  hierarchy: `account_type` is the only grouping. An optional `closed_on` ends
  the account's managed period.
- **Category.** A fixed two-level hierarchy, category group → category,
  flattened onto the category row. Only categories are assigned, through an
  allocation; groups are for rollups.
- **Date.** A `date` is its own conformed key. `ReportingMonth` derives from
  it. The contract has no calendar table.

All dimensions are Type 1. Renaming an account or regrouping a category
restates every report. Two things keep that from erasing the reasoning behind a
past decision: dimension keys never change meaning, and every category rename,
regrouping, retirement, and direction change is appended to
[`category-changes.md`](../domains/category-changes.md) when it is made.
Reproducing a report exactly as it was read needs the publication it was built
from, which is issue #8's.

Deliberately reclassifying old transactions is a change to the facts'
classification, not a dimension change. Now that a category reaches a
transaction through an allocation, that change has a row of its own to record;
its history is still issue #8's.

Dimension keys are durable, household-assigned identifiers such as
`joint-current` or `groceries`. They are immutable and never reused for a
different meaning. They are not surrogate keys and are never
derived from bank identifiers. `transaction_id` is derived from the Silver
canonical transaction identity (issue #5), so rebuilds keep it stable.

## Balance Chain Evaluation

For each account, walk its transactions in `account_sequence` order. The
sequence follows `transaction_date`, then Silver's deterministic order within a
transaction date. Gold keeps an anchor, the last known bank-stated balance, and
the sum of amounts booked since that anchor.

| Condition for transaction *t* | `balance_check` | Anchor afterwards |
| --- | --- | --- |
| `balance_after` is null | `missing_balance` | Unchanged; *t*'s amount joins the running sum. |
| No anchor exists yet | `opening` | *t*'s `balance_after`. |
| `balance_after == anchor + amounts since anchor + amount` | `consistent` | *t*'s `balance_after`. |
| Otherwise | `break` | *t*'s `balance_after` (re-anchor, so one break does not cascade). |

Bridging across a missing balance verifies the chain. It never invents the
missing value.

## Coverage

Gold applies ADR-006's whole-period evidence rules. A link joins consecutive
booked transactions in `(transaction_date, day_sequence)` order. It is verified
when both balances exist and the later balance equals the earlier balance plus
the later amount. Otherwise it is broken. Its span includes both transaction
dates. Bridging a missing balance for `balance_check` does not make either
adjacent link verified.

For each account and month of its managed period:

- **`complete`**: `coverage_start` is before the month's first day,
  `evidence_through` reaches its last day, and every link whose span overlaps
  the month is verified, including links into and out of the month.
- **`no_data`**: the account's admitted export evidence does not reach into
  the month at all.
- **`partial`**: otherwise. This includes the first managed month, evidence
  ending inside a month, and every month overlapped by a broken link.

A quiet month inside verified evidence is `complete` with zero activity; carry
the last bank-stated balance into its opening and closing snapshot fields.
For a quiet month with partial or absent evidence, both balances are null.
GoldAccount retains `coverage_start` and `evidence_through`, so consumers can
report an account with no transactions as `no_data` even before it has a
managed period. No account may disappear merely because it has no transactions.

## Worked Example (synthetic)

Two open DKK household accounts: `joint-current` (current) and
`joint-savings` (savings). Categories: `salary` and `interest` (group
`income`, direction `income`), `rent` and `utilities` (group `housing`),
`groceries` (group `food`), all three with direction `expense`. The latest
published month is 2026-04. Both accounts have an admitted export dated
2026-05-08 whose declared `covers_through` is 2026-05-08 as well, so by the
formula in [`silver-layer.md`](silver-layer.md#evidence-through) evidence
reaches through 2026-05-07 and April is past the provisional window. Gold
carries that value; it never derives it from an export date itself.

`joint-current` transactions. The `category` column is each transaction's
single allocation, shown inline to keep the example readable; in the model it is
a `GoldCategoryAllocation` row of its own, carrying the same account and date
and the transaction's whole amount:

| seq | transaction_date | amount | type | category | transfer | balance_after | check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-01-14 | 25,000.00 | income | salary | | 25,400.00 | opening |
| 2 | 2026-01-20 | -3,000.00 | transfer | | T1 | 22,400.00 | consistent |
| 3 | 2026-01-28 | -842.50 | expense | groceries | | 21,557.50 | consistent |
| 4 | 2026-02-02 | -8,500.00 | expense | rent | | 13,057.50 | consistent (21,557.50 − 8,500.00) |
| 5 | 2026-02-02 | -640.00 | expense | groceries | | 12,417.50 | consistent |
| 6 | 2026-02-12 | 120.00 | refund | groceries | | 12,537.50 | consistent |
| 7 | 2026-02-25 | 25,000.00 | income | salary | | 37,537.50 | consistent |
| 8 | 2026-03-02 | -450.00 | unknown | | | 36,587.50 | break (expected 37,087.50) |
| 9 | 2026-03-20 | -1,000.00 | expense | utilities | | 35,587.50 | consistent |
| 10 | 2026-04-01 | -8,500.00 | expense | rent | | 27,087.50 | consistent |
| 11 | 2026-04-24 | 25,000.00 | income | salary | | 52,087.50 | consistent |

February's allocations on `joint-current`, written out in full:

| allocation_id | transaction | account | date | category | amount |
| --- | --- | --- | --- | --- | --- |
| …seq4/rent | seq 4 | joint-current | 2026-02-02 | rent | -8,500.00 |
| …seq5/groceries | seq 5 | joint-current | 2026-02-02 | groceries | -640.00 |
| …seq6/groceries | seq 6 | joint-current | 2026-02-12 | groceries | 120.00 |
| …seq7/salary | seq 7 | joint-current | 2026-02-25 | salary | 25,000.00 |

A `transfer`, `adjustment`, or `unknown` transaction has no allocation at all,
so seq 2 (a January transfer) and seq 8 (a March `unknown`) appear in no
allocation table. Were seq 5 one day divided into 510.00 of groceries and
130.00 of homeware, it would have two rows here summing to -640.00, the
groceries row keeping its `allocation_id`, and nothing else in this document or
in any consumer query would change.

`joint-savings` transactions:

| seq | transaction_date | amount | type | category | transfer | balance_after | check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-01-20 | 3,000.00 | transfer | | T1 | 53,000.00 | opening |
| 2 | 2026-04-30 | 12.40 | income | interest | | 53,012.40 | consistent |

Monthly balance snapshots:

| account | month | opening | closing | coverage | why |
| --- | --- | --- | --- | --- | --- |
| joint-current | 2026-01 | 400.00 | 21,557.50 | partial | First managed month. |
| joint-current | 2026-02 | 21,557.50 | 37,537.50 | partial | Every check is consistent, but the March break's span starts at seq 7. |
| joint-current | 2026-03 | 37,037.50 | 35,587.50 | partial | Break at seq 8. The opening is 500.00 below February's closing, which shows the gap. |
| joint-current | 2026-04 | 35,587.50 | 52,087.50 | complete | 35,587.50 − 8,500.00 + 25,000.00 = 52,087.50. |
| joint-savings | 2026-01 | 50,000.00 | 53,000.00 | partial | First managed month. |
| joint-savings | 2026-02 | 53,000.00 | 53,000.00 | complete | Quiet month inside verified export evidence. |
| joint-savings | 2026-03 | 53,000.00 | 53,000.00 | complete | Quiet month inside verified export evidence. |
| joint-savings | 2026-04 | 53,000.00 | 53,012.40 | complete | Consistent with the January anchor. |

What consumers can and cannot derive:

- April household balance: 52,087.50 + 53,012.40 = 105,099.90. Balances are
  summed across accounts for the same month, and both rows are `complete`.
- Summing `joint-current` closing balances over February–April is
  meaningless: balances are never summed across months.
- February (analytics): income 25,000.00 and expenses 9,020.00, summed over
  transactions; `groceries` spending 640.00 − 120.00 = 520.00 and the `housing`
  group 8,500.00, summed over allocations. The two agree because a
  transaction's allocations sum to its amount: 8,500.00 + 520.00 = 9,020.00.
  The report must show `joint-current` as `partial` and `joint-savings` as
  `complete`.
- March: unclassified money in is 0.00, money out is −450.00, and count is 1.
- January: transfer T1 is excluded from income and expenses, and both legs
  stay visible in account activity.
- `joint-savings` February and March are verified quiet months. A requested
  June beyond the publication has no data and must not be read as zero.
- The DKK 500.00 break is between admitted exports, so ADR-010 does not
  quarantine either internally consistent export. It still makes February
  and March partial under ADR-006.
- Missing balances remain a separate fixture for a source that states no
  balances: its transactions have `missing_balance` and its covered months
  are partial. A balance-stating export with a missing balance is quarantined
  under ADR-010 and never reaches this Gold example.

## Not in the First Release

Authored category splits — a workflow for dividing one transaction across
several allocations, and the rule for which allocation a refund reverses. The
allocation fact exists from the first release, always with one allocation per
classified transaction. Also out: Type 2 dimensions, counterparty or merchant
dimension, person dimension, account hierarchy, daily balance snapshots,
budget facts, and audit/publication dimensions (issue #8).

## Consumers

Analytics, forecasting, and API services, through `GoldRepository` only.
Review and audit tooling may also use `GoldLineageRepository`.

## Ownership

Gold Agent
