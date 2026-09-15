# Gold Layer

## Purpose

Represent household financial facts as a small dimensional model. Gold stays
stable when source systems change.

The normative field list, invariants, and interfaces are in the
[Gold contract](gold-contract.md). This document explains the model behind
them: business processes, grains, dimensions, and the balance-chain and
coverage rules. Field names here are illustrative references to that
contract. See [ADR-007](../decisions/ADR-007-dimensional-gold-model.md) and
[ADR-008](../decisions/ADR-008-single-category-per-transaction.md).

## Responsibilities

- Publish the account and category dimensions from the household registries.
- Materialize one Gold transaction per booked Silver transaction and classify
  it: manual decisions, then transfer matching, then classification rules
  ([`classification.md`](classification.md)).
- Publish classification lineage and classification review items for review
  tooling.
- Evaluate each account's balance chain and publish a balance check per
  transaction.
- Publish a monthly balance snapshot with coverage for every month of each
  account's managed period.
- Keep lineage behind the privileged lineage interface.

## Business Processes and Grains

| Process | Fact | Grain |
| --- | --- | --- |
| Booking money movements on an account | `GoldTransaction` | One booked transaction on one account, never split across categories. |
| Observing account balances | `MonthlyBalanceSnapshot` | One account for one reporting month of its managed period, including months with no transactions. |

Budgets and forecasts are out of scope for the first release. They appear in
the bus matrix only to check that the dimensions will conform later.

## Bus Matrix

| Process | Date | Account | Category |
| --- | --- | --- | --- |
| Booked transactions | ✓ (booking date) | ✓ | ✓ (when classified) |
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
  flattened onto the category row. Only categories are assigned; groups are
  for rollups.
- **Date.** A `date` is its own conformed key. `ReportingMonth` derives from
  it. The contract has no calendar table.

All dimensions are Type 1. Renaming an account or regrouping a category
restates every report. Deliberately reclassifying old transactions is a change
to the facts' classification, not a dimension change. Its history belongs to
issue #8.

Dimension keys are durable, household-assigned identifiers such as
`joint-current` or `groceries`. They are not surrogate keys and are never
derived from bank identifiers. `transaction_id` is derived from the Silver
canonical transaction identity (issue #5), so rebuilds keep it stable.

## Balance Chain Evaluation

For each account, walk its transactions in `account_sequence` order. The
sequence follows `booking_date`, then Silver's deterministic order within a
booking date. Gold keeps an anchor, the last known bank-stated balance, and
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

For each account and each month of its managed period:

- **`no_data`**: the account has no transactions in the month.
- **`partial`**: any one of the following holds:
  - the month is the first month of the managed period;
  - a transaction in the month has a check other than `consistent`;
  - the month lies within a break's span: every month with transactions, from
    the month of the anchor before the break through the break's month.
- **`complete`**: otherwise.

The break span is needed because a missing movement between the last trusted
balance and the break could be on either side of a month boundary. A
`no_data` month inside a break span stays `no_data`.

## Worked Example (synthetic)

Two open DKK household accounts: `joint-current` (current) and
`joint-savings` (savings). Categories: `salary` and `interest` (group
`income`, direction `income`), `rent` and `utilities` (group `housing`),
`groceries` (group `food`), all three with direction `expense`. The latest
published month is 2026-04.

`joint-current` transactions:

| seq | booking_date | amount | type | category | transfer | balance_after | check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-01-14 | 25,000.00 | income | salary | | 25,400.00 | opening |
| 2 | 2026-01-20 | -3,000.00 | transfer | | T1 | 22,400.00 | consistent |
| 3 | 2026-01-28 | -842.50 | expense | groceries | | null | missing_balance |
| 4 | 2026-02-02 | -8,500.00 | expense | rent | | 13,057.50 | consistent (22,400.00 − 842.50 − 8,500.00) |
| 5 | 2026-02-02 | -640.00 | expense | groceries | | 12,417.50 | consistent |
| 6 | 2026-02-12 | 120.00 | refund | groceries | | 12,537.50 | consistent |
| 7 | 2026-02-25 | 25,000.00 | income | salary | | 37,537.50 | consistent |
| 8 | 2026-03-02 | -450.00 | unknown | | | 36,587.50 | break (expected 37,087.50) |
| 9 | 2026-03-20 | -1,000.00 | expense | utilities | | 35,587.50 | consistent |
| 10 | 2026-04-01 | -8,500.00 | expense | rent | | 27,087.50 | consistent |
| 11 | 2026-04-24 | 25,000.00 | income | salary | | 52,087.50 | consistent |

`joint-savings` transactions:

| seq | booking_date | amount | type | category | transfer | balance_after | check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-01-20 | 3,000.00 | transfer | | T1 | 53,000.00 | opening |
| 2 | 2026-04-30 | 12.40 | income | interest | | 53,012.40 | consistent |

Monthly balance snapshots:

| account | month | opening | closing | coverage | why |
| --- | --- | --- | --- | --- | --- |
| joint-current | 2026-01 | 400.00 | null | partial | First managed month; seq 3 has no balance, so there is no stated closing. |
| joint-current | 2026-02 | 21,557.50 | 37,537.50 | partial | Every check is consistent, but the March break's span starts at seq 7. |
| joint-current | 2026-03 | 37,037.50 | 35,587.50 | partial | Break at seq 8. The opening is 500.00 below February's closing, which shows the gap. |
| joint-current | 2026-04 | 35,587.50 | 52,087.50 | complete | 35,587.50 − 8,500.00 + 25,000.00 = 52,087.50. |
| joint-savings | 2026-01 | 50,000.00 | 53,000.00 | partial | First managed month. |
| joint-savings | 2026-02 | null | null | no_data | No transactions. |
| joint-savings | 2026-03 | null | null | no_data | No transactions. |
| joint-savings | 2026-04 | 53,000.00 | 53,012.40 | complete | Consistent with the January anchor. |

What consumers can and cannot derive:

- April household balance: 52,087.50 + 53,012.40 = 105,099.90. Balances are
  summed across accounts for the same month, and both rows are `complete`.
- Summing `joint-current` closing balances over February–April is
  meaningless: balances are never summed across months.
- February (analytics): income 25,000.00; expenses 9,140.00; `groceries`
  spending 640.00 − 120.00 = 520.00; `housing` group 8,500.00. The report
  must show `joint-current` as `partial` and `joint-savings` as `no_data`.
- March: the unclassified total is −450.00.
- January: transfer T1 is excluded from income and expenses, and both legs
  stay visible in account activity. It is a `same_day` pair under the
  classification policy.
- `joint-savings` February and March are `no_data` even though the April
  chain shows no movement was missed. Import coverage windows could one day
  prove quiet months; that is an open follow-up, and the coverage semantics
  are not changed here.

## Not in the First Release

Category allocations or splits, Type 2 dimensions, counterparty or merchant
dimension, person dimension, account hierarchy, daily balance snapshots,
budget facts, and audit/publication dimensions (issue #8).

## Consumers

Analytics, forecasting, and API services, through `GoldRepository` only.
Review and audit tooling may also use `GoldLineageRepository`.

## Ownership

Gold Agent
