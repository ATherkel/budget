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
| `transaction_date` | `date` | Yes | Date the source assigns to the transaction (for Danske, the purchase date, which can precede booking by days); reporting period derives from it. |
| `amount` | `Decimal` | Yes | Signed monetary amount. |
| `currency` | ISO 4217 string | Yes | Currency, initially `DKK`. |
| `description` | string | Yes | Normalized human-readable transaction text. |
| `transaction_type` | enum | Yes | `income`, `expense`, `transfer`, `adjustment`, or `unknown`. |
| `category_id` | UUID/string/null | Conditional | Required for classified income/expense, and for an adjustment that nets a refund against the category it reverses; null permitted for transfer, unknown, and adjustments with no originating category. |
| `balance` | `Decimal`/null | No | Bank-stated account balance immediately after this transaction, as stated by the latest export covering its date; a late booking can change it. Drives balance-chain reconciliation and coverage; null when the source omitted it, which is a discrepancy, not an assumed zero. |
| `counterparty` | string/null | No | Normalized merchant, person, or organisation when known. |
| `transfer_group_id` | UUID/string/null | No | Groups two or more internal transfer legs when confidently matched. |
| `classification_source` | enum | Yes | `rule`, `manual`, `imported`, or `unclassified`. |
| `classification_version` | string | Yes | Rule-set or manual-policy version that produced the classification. |
| `reporting_month` | `YYYY-MM` | Yes | Derived solely from `transaction_date`. |
| `created_at` | UTC datetime | Yes | Time this Gold version was materialized. |

## Invariants

1. `amount` is represented with fixed decimal precision; no float enters the
   contract.
2. `reporting_month == transaction_date.strftime("%Y-%m")`.
3. `transaction_type=expense` has a negative amount; `income` has a positive
   amount. Corrections that do not obey this convention use `adjustment` and
   need an explanation.
4. A `transfer` is excluded from expense, income, savings-rate, and category
   spending totals. It remains visible in account activity.
5. Every Gold record can be traced through `silver_transaction_id` to retained
   Bronze provenance.
6. Classification is never silently destructive: a materialized Gold version
   records how it was derived and can be rebuilt.
7. `transaction_date` is used exactly as supplied by the source; no timezone
   conversion is applied at any layer.
8. Only source rows in a completed/settled booking status are materialized as
   `GoldTransaction`. Pending or unsettled rows remain in Bronze/Silver only.
9. For two chronologically adjacent transactions on the same account,
   `balance == previous_balance + amount` when both are present; the
   account's first transaction is trusted as its opening balance. A break in
   this chain, or a missing `balance`, is never corrected or hidden — it is
   surfaced as reduced coverage (see `analytics-layer.md`), not silently
   assumed. For balance-stating sources, an export with a missing balance or
   an internal break is quarantined before Silver (ADR-010), so `balance` is
   null only for sources that state no balances.
10. `silver_transaction_id` is stable across re-imports and rebuilds
    (ADR-009), so classifications and manual decisions keep their targets.

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
```

Consumers may filter the returned records and aggregate them. They may not
assume a database table name, source-system identifier, or raw CSV column.

## Contract Fixtures

Before analytics or UI work begins, provide fixtures covering: income,
expense, paired transfer, unmatched transfer candidate, unclassified record,
and a manually overridden category. Fixtures contain synthetic data only.

## Open Decisions

- Define the household's account taxonomy and account ownership metadata.
- Decide whether bank-provided categories are retained as a separate Gold
  attribution or only as Silver provenance.
- Define the transfer matching confidence threshold and review workflow.
