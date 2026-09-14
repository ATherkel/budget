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
| `amount` | `Decimal` | Yes | Signed monetary amount. |
| `currency` | ISO 4217 string | Yes | Currency, initially `DKK`. |
| `description` | string | Yes | Normalized human-readable transaction text. |
| `transaction_type` | enum | Yes | `income`, `expense`, `transfer`, `adjustment`, or `unknown`. |
| `category_id` | UUID/string/null | Conditional | Required for classified income/expense; null is permitted for transfer, adjustment, and unknown. |
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
