---
type: architecture
---
# Gold Layer

## Summary

- Gold models household financial facts as a small dimensional model that
  stays stable when sources change.
- Three facts: booked transactions, their category allocations, and a monthly
  balance snapshot per account; three dimensions: account, category, date.
- This doc explains the model, the balance chain and coverage. The
  [Gold contract](gold-contract.md) owns the fields, invariants and
  interfaces; decisions are
  [ADR-007](../decisions/ADR-007-dimensional-gold-model.md) and
  [ADR-008](../decisions/ADR-008-category-allocation-grain.md).

## Responsibilities

- Publish the account and category dimensions from the household registries.
- Materialize one Gold transaction per booked Silver transaction, classify it
  ([`classification.md`](classification.md)), and publish its allocation.
- Publish classification lineage and review items, behind the privileged
  lineage interface.
- Evaluate each account's balance chain, with a balance check per transaction.
- Publish a monthly balance snapshot with coverage for every month of each
  account's managed period.

## Business Processes and Grains

| Process | Fact | Grain |
| --- | --- | --- |
| Booking money movements on an account | `GoldTransaction` | One booked transaction on one account. |
| Assigning a transaction to a category | `GoldCategoryAllocation` | One category allocation of one booked transaction. Exactly one per classified transaction in the first release. |
| Observing account balances | `MonthlyBalanceSnapshot` | One account for one reporting month of its managed period, including months with no transactions. |

Category assignment has its own grain because it is the household's judgement,
not a property of the movement, and one movement can belong to several
categories: dividing a mixed purchase later changes no transaction fact or
consumer query ([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).

## Bus Matrix

| Process | Date | Account | Category |
| --- | --- | --- | --- |
| Booked transactions | ✓ (transaction date) | ✓ | — |
| Category allocations | ✓ (transaction date) | ✓ | ✓ |
| Monthly balance snapshots | ✓ (month) | ✓ | — |
| *Future: budget targets* | ✓ (month) | — | ✓ |

Budgets appear only to check that the dimensions will conform. Currency is an
account attribute, not a dimension. A future budget is compared with actuals
only after both are aggregated to category × month; joined to transactions, it
would count once per transaction.

## Dimensions

- **Account.** Only accounts inside the reporting boundary (`ownership_scope`
  `household` or `person`), of type `current` or `savings`. No person dimension
  or hierarchy; `account_type` is the only grouping. `closed_on` ends the
  managed period.
- **Category.** A fixed two-level hierarchy, group → category, flattened onto
  the category row. Only categories are assigned; groups are for rollups.
- **Date.** A `date` is its own conformed key, and `ReportingMonth` derives
  from it. There is no calendar table.

All dimensions are Type 1: a rename or regroup restates every report. Keys
never change meaning, every category change is appended to
[`category-changes.md`](../domains/category-changes.md), and a report exactly
as it was read is an as-was view ([`publications.md`](publications.md)).
Reclassifying old transactions changes allocations, not a dimension; its
history is the publications and the decision log.

Dimension keys are durable household identifiers such as `joint-current` or
`groceries`: immutable, never reused, not surrogates, never derived from bank
identifiers. `transaction_id` derives from Silver's canonical identity, so
rebuilds keep it.

## Balance Chain Evaluation

For each account, walk its transactions in `account_sequence` order
(`transaction_date`, then Silver's deterministic order within a date), keeping
an anchor, the last bank-stated balance, and the sum booked since it.

| Condition for transaction *t* | `balance_check` | Anchor afterwards |
| --- | --- | --- |
| `balance_after` is null | `missing_balance` | Unchanged; *t*'s amount joins the running sum. |
| No anchor exists yet | `opening` | *t*'s `balance_after`. |
| `balance_after == anchor + amounts since anchor + amount` | `consistent` | *t*'s `balance_after`. |
| Otherwise | `break` | *t*'s `balance_after` (re-anchor, so one break does not cascade). |

Bridging a missing balance verifies the chain; it never invents the value.

## Coverage

Gold applies ADR-006's whole-period evidence rules. A **link** joins
consecutive booked transactions in `(transaction_date, day_sequence)` order,
spanning both dates. It is verified when both balances exist and the later
equals the earlier plus the later amount, and broken otherwise; bridging for
`balance_check` does not verify it. A final link runs from the last transaction
onward, verified only when that transaction states its balance, so no later
month is `complete` until an import adds one that does (whose own month stays
`partial`).

For each account and month of its managed period:

- **`complete`**: one evidence range
  ([`silver-layer.md`](silver-layer.md#evidence-ranges)) covers the whole
  month, and every link overlapping it, into and out of the month included, is
  verified.
- **`no_data`**: no evidence range reaches into the month.
- **`partial`**: otherwise, such as the first managed month, evidence starting,
  ending or gapping inside the month, or a broken link, the final one included.

A quiet month inside verified evidence is `complete` with zero activity and the
last stated balance as opening and closing. With partial or absent evidence,
both balances are null. `GoldAccount` keeps `coverage_start` and
`evidence_through`, so an account with no transactions still reports
`no_data` and never disappears.

### Late bookings settled

A transaction can be booked days after its date, so a month can change after
it ends. For each account and month of its managed period,
`late_bookings_settled` is true when a run counted in the account's evidence
has an export date at least the **late-booking window** after the month's last
day *and* a declared range (`covers_from` through `covers_through`) that
includes that day. The counted runs are those behind the evidence ranges:
admitted runs and `repeat`s of an admitted payload, so a quiet account
repeating the same bytes settles normally. Silver passes each one's export date
and range as an `EvidenceExport`
([`silver-layer.md`](silver-layer.md#evidence-ranges)); Gold never reads
Bronze.

The window is the profile's `[gold] late_booking_days`, 7 by default
([`operations.md`](operations.md#selecting-a-profile)). The build is given it,
refuses a value outside whole days 0 to 366, and the recipe records it
([`publications.md`](publications.md#the-recipe)), so a rebuild gives the same
flags. Analytics combines the flag with the reference date into the
provisional label
([`presentation-layer.md`](presentation-layer.md#data-trust-display)).

## Worked Example (synthetic)

Two open DKK household accounts: `joint-current` (current) and
`joint-savings` (savings). Categories: `salary` and `interest` (group
`income`, direction `income`), `rent` and `utilities` (group `housing`),
`groceries` (group `food`), all three with direction `expense`. Both accounts
have one admitted export dated 2026-05-08, declared from 2026-01-01 through
2026-05-08, so each has one [evidence range](silver-layer.md#evidence-ranges):
`coverage_start` 2026-01-01, `evidence_through` 2026-05-08. The latest
published month is therefore 2026-05, and both accounts have a May row without
a May transaction. The export came more than 7 days after April and covers
April's last day, so every row through April has `late_bookings_settled` true;
May's do not, since settling May needs an export produced on or after
2026-06-07 that covers 2026-05-31.

`joint-current` transactions. The `category` column is each transaction's
single allocation, shown inline; in the model it is a `GoldCategoryAllocation`
row with the same account, date and whole amount:

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

A `transfer`, `adjustment` or `unknown` transaction has no allocation, so seq 2
and seq 8 appear in none. Were seq 5 divided into 510.00 of groceries and
130.00 of homeware, it would have two rows summing to -640.00, the groceries
row keeping its `allocation_id`, and no consumer query would change.

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
| joint-current | 2026-05 | | | partial | Evidence ends on 2026-05-08, inside the month. A quiet month with partial evidence has null balances. |
| joint-savings | 2026-01 | 50,000.00 | 53,000.00 | partial | First managed month. |
| joint-savings | 2026-02 | 53,000.00 | 53,000.00 | complete | Quiet month inside verified export evidence. |
| joint-savings | 2026-03 | 53,000.00 | 53,000.00 | complete | Quiet month inside verified export evidence. |
| joint-savings | 2026-04 | 53,000.00 | 53,012.40 | complete | Consistent with the January anchor. |
| joint-savings | 2026-05 | | | partial | As for `joint-current`. |

What consumers can and cannot derive:

- April household balance: 52,087.50 + 53,012.40 = 105,099.90, summed across
  accounts in one month, both `complete`. Balances are never summed across
  months.
- February: income 25,000.00 and expenses 9,020.00 over transactions;
  `groceries` 640.00 − 120.00 = 520.00 and `housing` 8,500.00 over
  allocations, which agree because allocations sum to their transaction:
  8,500.00 + 520.00 = 9,020.00. `joint-current` shows `partial`,
  `joint-savings` `complete`.
- March: unclassified money in 0.00, out −450.00, count 1.
- January: transfer T1, a `same_day` pair
  ([`classification.md`](classification.md)), is excluded from income and
  expenses; both legs stay in account activity.
- `joint-savings` February and March are verified quiet months. A June beyond
  the publication has no data, not zero.
- May is provisional (`late_bookings_settled` false) and `partial` (evidence
  ends inside it), so its zero activity is unconfirmed. April is not
  provisional unless the reference date falls in April.
- The DKK 500.00 break lies between admitted exports, so ADR-010 quarantines
  neither, but it makes February and March partial under ADR-006.
- A source that states no balances is a separate fixture: `missing_balance`
  throughout and partial months. A balance-stating export missing a balance is
  quarantined (ADR-010) unless *accept discrepancy* admits it, giving
  `missing_balance` too (ADR-016).

## Not in the First Release

Authored category splits (dividing one transaction across allocations, and
which allocation a refund reverses), Type 2 dimensions, counterparty, merchant
or person dimensions, account hierarchy, daily balance snapshots, budget facts,
and audit or publication dimensions. Publication metadata describes the whole
publication, not a dimension ([`publications.md`](publications.md)).

## Consumers

Analytics and forecasting, through `GoldRepository` and `GoldPublications`
only. Presentation and APIs read analytics reports, never Gold. Review and
audit tooling may also use `GoldLineageRepository`.

## Ownership

Gold Agent
