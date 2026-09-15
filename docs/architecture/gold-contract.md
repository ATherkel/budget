# Gold Data Contract

## Status

Version `0.1` — proposed for the CSV MVP. Changes are backward-incompatible
unless a new contract version is introduced and downstream consumers migrate.

## Purpose

Gold is the stable business-facing representation of household financial facts.
Analytics, forecasting, APIs, and presentation may read Gold only through this
contract. They must not import a connector, parse CSV, or query Bronze/Silver
storage.

Gold is derived from Silver. It is not the original bank record and it remains
rebuildable when classification logic changes.

## `GoldTransaction`

Every record represents one booked transaction on one account. Amounts are
signed in the account's currency: money into the account is positive and money
out is negative.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `gold_transaction_id` | UUID/string | Yes | Stable identifier for this Gold record/version. |
| `silver_transaction_id` | UUID/string | Yes | Traceable parent Silver record. |
| `account_id` | UUID/string | Yes | Stable household account identifier. |
| `booking_date` | `date` | Yes | Bank booking date; reporting period derives from it. |
| `day_sequence` | int | Yes | Position among the account's transactions on the same `booking_date`, ascending in the bank's own row order. Values ascend but need not be consecutive. |
| `amount` | `Decimal` | Yes | Signed monetary amount. |
| `currency` | ISO 4217 string | Yes | Currency, initially `DKK`. |
| `description` | string | Yes | Normalized human-readable transaction text. |
| `transaction_type` | enum | Yes | `income`, `expense`, `transfer`, `adjustment`, or `unknown`. |
| `category_id` | UUID/string/null | Conditional | Required for classified income/expense. An adjustment with a `category_id` is a refund and nets against that category; an adjustment without one is an uncategorized correction. Null for transfer and unknown. |
| `category_direction` | enum/null | Conditional | `income` or `expense`: the direction of the `category_id` category, so consumers can net refunds without a category lookup. Null exactly when `category_id` is null. |
| `balance` | `Decimal`/null | No | Bank-stated account balance immediately after this transaction. Drives balance-chain reconciliation and coverage; null when the source omitted it, which is a discrepancy, not an assumed zero. |
| `counterparty` | string/null | No | Normalized merchant, person, or organisation when known. |
| `transfer_group_id` | UUID/string/null | No | Groups two or more internal transfer legs when confidently matched. |
| `classification_source` | enum | Yes | `rule`, `manual`, `imported`, or `unclassified`. |
| `classification_version` | string | Yes | Rule-set or manual-policy version that produced the classification. |
| `reporting_month` | `YYYY-MM` | Yes | Derived solely from `booking_date`. |
| `created_at` | UTC datetime | Yes | Time this Gold version was materialized. |

## Invariants

1. `amount` is represented with fixed decimal precision; no float enters the
   contract.
2. `reporting_month == booking_date.strftime("%Y-%m")`.
3. `transaction_type=expense` has a negative amount; `income` has a positive
   amount. Corrections that do not obey this convention use `adjustment` and
   need an explanation.
4. A `transfer` is excluded from expense, income, savings-rate, and category
   spending totals. It remains visible in account activity.
5. Every Gold record can be traced through `silver_transaction_id` to retained
   Bronze provenance.
6. Classification is never silently destructive: a materialized Gold version
   records how it was derived and can be rebuilt.
7. `booking_date` is used exactly as supplied by the source; no timezone
   conversion is applied at any layer.
8. Only Silver transactions with `booking_status=booked` are materialized as
   `GoldTransaction`. `pending` and `cancelled` rows remain in Bronze/Silver
   only and take no part in the balance chain.
9. Gold carries `balance` exactly as the source states it and never corrects,
   fills, or reconciles it. `(account_id, booking_date, day_sequence)` is
   unique, so each account's transactions have one total order. Whether
   consecutive balances chain is evaluated by analytics (`analytics-layer.md`,
   Coverage); Gold does not guarantee that the chain holds.

## `GoldAccount`

One record per registered household account, whether or not it has
transactions yet. Account taxonomy and ownership attributes belong to issue #6.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `account_id` | UUID/string | Yes | Matches `GoldTransaction.account_id`. |
| `active` | bool | Yes | Whether the account is currently in use. |
| `coverage_start` | `date`/null | No | `booking_date` of the account's first transaction, whose balance is trusted as the opening balance. Null when the account has no transactions. |
| `evidence_through` | `date`/null | No | Last date the account's imported exports are known to cover: the day before its latest export date, because the export day itself may still be booking. Null when no export of the account has been imported. |

## Consumer Interface

The implementation must expose a narrow repository/service interface. The
precise persistence technology is not part of this contract.

```python
class GoldTransactionRepository(Protocol):
    def list_transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Sequence[str] | None = None,
    ) -> Sequence[GoldTransaction]: ...

    def boundary_transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Sequence[str] | None = None,
    ) -> Sequence[GoldTransaction]: ...

    def list_accounts(self) -> Sequence[GoldAccount]: ...
```

- `list_transactions` returns records ordered by `account_id`, `booking_date`,
  `day_sequence`.
- `boundary_transactions` returns, for each account, its last transaction
  before `start_date` and its first transaction after `end_date`, where they
  exist. Analytics needs them to check the balance links into and out of a
  period.
- `list_accounts` returns every registered account, including accounts with no
  transactions.

Consumers may filter the returned records and aggregate them. They may not
assume a database table name, source-system identifier, or raw CSV column.

## Contract Fixtures

Before analytics or UI work begins, provide fixtures covering: income,
expense, paired transfer, unmatched transfer candidate, unclassified record,
a manually overridden category, a refund, an uncategorized adjustment,
several transactions on one day, a
balance-chain break, and an account with no transactions. Fixtures contain
synthetic data only.

## Open Decisions

- Define the household's account taxonomy and account ownership metadata.
- Decide whether bank-provided categories are retained as a separate Gold
  attribution or only as Silver provenance.
- Define the transfer matching confidence threshold and review workflow.
