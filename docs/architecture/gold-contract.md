# Gold Data Contract

## Status

Version `0.2`, proposed for the CSV MVP. The dimensional model amends the
still-proposed 0.2 contract in place, retaining the accepted reporting evidence
from issue #4; see [Changes in 0.2](#changes-in-02), which lists every change
since 0.1, including the ones made by the earlier 0.2 draft. Changes are
backward-incompatible unless a new contract version is introduced and
downstream consumers migrate. The contract stays proposed until the readiness
review (issue #12) approves it.

## Purpose

Gold is the stable business-facing representation of household financial facts.
Analytics, forecasting, APIs, and presentation may read Gold only through this
contract. They must not import a connector, parse CSV, or query Bronze/Silver
storage.

Gold is derived from Silver, the household account and category registries,
and classification inputs. It is not the original bank record, and it can be
rebuilt when classification logic changes.

The dimensional model behind this contract (processes, grains, the bus
matrix, balance-chain evaluation, and a worked synthetic example) is described
in [`gold-layer.md`](gold-layer.md) and [ADR-007](../decisions/ADR-007-dimensional-gold-model.md).
This document is the only normative schema. Where another document shows
Gold fields, it is illustrative.

## Shared Value Types

| Type | Values / shape | Meaning |
| --- | --- | --- |
| `ReportingMonth` | `YYYY-MM` | Calendar month. `ReportingMonth.of(d)` is derived solely from a `date`. |
| `AccountType` | `current`, `savings` | First-release account types. The account domain reserves further types; Gold rejects them until a reporting policy exists. |
| `OwnershipScope` | `household`, `person` | Scopes inside the reporting boundary. `external` accounts are never Gold accounts. |
| `CategoryDirection` | `income`, `expense` | Which measure a category reports under. |
| `TransactionType` | `income`, `expense`, `refund`, `transfer`, `adjustment`, `unknown` | Household interpretation of a booked transaction. |
| `BalanceCheck` | `opening`, `consistent`, `break`, `missing_balance` | Result of the balance-chain check for one transaction. |
| `Coverage` | `complete`, `partial`, `no_data` | Trust status of one account for one reporting month. |

Monetary values are `Decimal` in the account's currency. No float enters the
contract.

## Dimensions

### `GoldAccount`

One row per account inside the reporting boundary. Type 1: attributes show the
current household interpretation.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `account_id` | string | Yes | Durable, household-assigned identifier. Never a bank account number or other source identifier. |
| `display_name` | string | Yes | Household-facing name. |
| `account_type` | `AccountType` | Yes | `current` or `savings`. |
| `ownership_scope` | `OwnershipScope` | Yes | `household` or `person`. |
| `currency` | ISO 4217 string | Yes | Currency of every amount and balance on this account. `DKK` in the first release. |
| `closed_on` | `date`/null | No | Date the account closed; null while open. Ends the account's managed period. |
| `coverage_start` | `date`/null | No | First booked transaction date; null for an account with no transactions. |
| `evidence_through` | `date`/null | No | Last date the account's imported exports are known to cover. Computed by Silver (`silver-layer.md`, *Evidence Through*) and carried through unchanged; Gold does not derive it. Null when no export of the account has been imported. |

### `GoldCategory`

One row per assignable category. The two-level hierarchy is flattened onto the
category: every category belongs to exactly one category group, and groups are
never assigned to transactions. Type 1: renaming or regrouping a category
restates all history.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `category_id` | string | Yes | Durable, household-assigned identifier. |
| `name` | string | Yes | Household-facing category name. |
| `group_id` | string | Yes | Durable identifier of the category group. |
| `group_name` | string | Yes | Household-facing category group name. |
| `direction` | `CategoryDirection` | Yes | `income` or `expense`. |

There is no stored calendar dimension in the contract. A `date` is its own
conformed date key, and `ReportingMonth` is derived from it. Persistence may
materialize a calendar table without changing this contract.

## Facts

### `GoldTransaction`

Grain: one booked transaction on one account
([ADR-008](../decisions/ADR-008-single-category-per-transaction.md): never
split across categories). Amounts are signed in the account's currency: money
into the account is positive and money out is negative.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `transaction_id` | string | Yes | Stable identifier, derived deterministically from the Silver canonical transaction identity, so a rebuild yields the same value. |
| `account_id` | string | Yes | References `GoldAccount`. |
| `transaction_date` | `date` | Yes | Source transaction date (Danske: purchase date), exactly as supplied; the reporting month derives from it (ADR-009). |
| `account_sequence` | int | Yes | Position in the account's booked history, starting at 1, following `(transaction_date, day_sequence)` from Silver (ADR-009). Used only for ordering; it is not an identity and may shift when earlier transactions are imported. |
| `amount` | `Decimal` | Yes | Signed amount in the account's currency. |
| `description` | string | Yes | Normalized human-readable transaction text. |
| `transaction_type` | `TransactionType` | Yes | Household interpretation. |
| `category_id` | string/null | Conditional | References `GoldCategory`. Required for `income`, `expense`, and `refund`; null for `transfer`, `adjustment`, and `unknown`. |
| `transfer_group_id` | string/null | No | Groups the legs of one internal transfer when confidently matched (policy: issue #7). |
| `balance_after` | `Decimal`/null | No | Bank-stated balance from the latest admitted export covering this date (ADR-009). Null only for sources that state no balances; inconsistent balance-stating exports are quarantined under ADR-010. |
| `balance_check` | `BalanceCheck` | Yes | Result of the balance-chain check for this transaction (see `gold-layer.md`). |

### `MonthlyBalanceSnapshot`

Grain: one account for one reporting month of its managed period. The managed
period runs from the month of the account's first booked transaction to the
month of `closed_on`, or to the latest reporting month present in the
published Gold data if the account is open. There is exactly one row per
month in that range, including months with no transactions.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `account_id` | string | Yes | References `GoldAccount`. |
| `month` | `ReportingMonth` | Yes | The reporting month. |
| `opening_balance` | `Decimal`/null | No | Balance immediately before the month's first transaction: that transaction's `balance_after` minus its `amount`. For a complete quiet month, carry the last bank-stated balance into both opening and closing. Null when the required balance is missing or the month is `no_data`. |
| `closing_balance` | `Decimal`/null | No | `balance_after` of the month's last transaction by `account_sequence`, bank-stated only. For a complete quiet month, carry the last bank-stated balance into both opening and closing. Null when the required balance is missing or the month is `no_data`. |
| `coverage` | `Coverage` | Yes | Trust status for this account and month (see `gold-layer.md`). |

Additivity: `amount` is additive across every dimension within one currency.
Balances are semi-additive: they may be summed across accounts for the same
month, never across months. `coverage` is non-additive.

## Invariants

1. Every `account_id` and `category_id` on a fact references a published
   dimension row. Every `GoldAccount` is inside the reporting boundary.
2. Each booked Silver transaction on a Gold account yields exactly one
   `GoldTransaction`. Only `booking_status=booked` rows qualify; pending and cancelled records remain provenance.
3. Sign convention: `expense` amounts are negative; `income` amounts are
   positive. A `refund` reverses its category's direction: positive for an
   expense category, negative for an income category. `adjustment` may take
   either sign and needs an explanation.
4. Category direction matches the type: `income` → an `income` category,
   `expense` → an `expense` category; a `refund` retains the category of
   the movement it reverses.

5. A `transfer` is excluded from income, expense, savings-rate, and category
   spending totals. It remains visible in account activity.
6. `transaction_date` is used exactly as supplied by the source. No timezone
   conversion is applied at any layer.
7. Per account, `account_sequence` runs 1, 2, 3, … without gaps, and
   `transaction_date` never decreases as `account_sequence` increases.
8. `balance_check` follows the balance-chain rules in `gold-layer.md`. A
   break or missing balance is never corrected or hidden.
9. `MonthlyBalanceSnapshot` has exactly one row per account per month of the
   managed period. When a row's `coverage` is `complete`,
   `opening_balance + sum(amounts in the month) == closing_balance`.
10. All first-release accounts use `DKK`. Consumers must never aggregate
    amounts or balances across different currencies.
11. No `transaction_date` falls after its account's `closed_on`.
12. A consumer reads exactly one Gold publication at a time. Which publication
    is selected, and identity across materializations, are defined by issue
    #8.

## Consumer Interface

Analytics, forecasting, APIs, and presentation-facing services depend on this
protocol only. The persistence technology is not part of this contract.
All date and month ranges are inclusive.

```python
class GoldRepository(Protocol):
    def accounts(self) -> Sequence[GoldAccount]: ...

    def categories(self) -> Sequence[GoldCategory]: ...

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldTransaction]: ...

    def monthly_balances(
        self,
        *,
        start_month: ReportingMonth,
        end_month: ReportingMonth,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[MonthlyBalanceSnapshot]: ...
```

Consumers may filter, join on dimension keys, and aggregate the returned
records. They may not assume a table name, a source-system identifier, or a
raw CSV column. A month with no `MonthlyBalanceSnapshot` row for an account is
outside that account's managed period. A requested month beyond the latest
published month has no data and must never be read as zero.

## Lineage Interface (privileged)

Lineage explains where a Gold fact came from. Review and audit tooling reads it,
for example the CLI classification-review and rebuild workflows (issues #7 and
#10). Analytics and presentation must not depend on it.

```python
class GoldLineageRepository(Protocol):
    def transaction_lineage(
        self, transaction_ids: Collection[str]
    ) -> Sequence[GoldTransactionLineage]: ...
```

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `transaction_id` | string | Yes | The Gold transaction explained. |
| `silver_transaction_id` | string | Yes | Traceable parent Silver record, and through it the retained Bronze provenance. |
| `classification_source` | enum | Yes | `rule`, `manual`, `imported`, or `unclassified`. |
| `classification_version` | string | Yes | Rule-set or manual-policy version that produced the classification. |

Transfer-match evidence and confidence are added to lineage by issue #7.
Publication and materialization metadata (such as when a version was built)
are added by issue #8.

## Contract Fixtures

Before analytics or UI work begins, provide synthetic fixtures covering:
income; expense; refund netting against its category; adjustment without a
category; paired transfer; unmatched transfer candidate; unknown transaction;
manually overridden category (visible through lineage); missing balance; chain
break that demotes the previous month; first managed month (`partial`);
complete quiet month; partial quiet month crossed by a broken link; `no_data` month beyond evidence; closed account; and two categories
sharing a group. The worked example in `gold-layer.md` covers most of these.

## Changes in 0.2

This table covers everything 0.2 changes since 0.1. Rows marked *(0.2 draft)*
were introduced by the earlier 0.2 draft and are superseded here, so a reader
migrating from either version finds the whole path in one place.

| 0.1 or the earlier 0.2 draft | 0.2 | Why |
| --- | --- | --- |
| `GoldTransactionRepository.list_transactions` | `GoldRepository` with accounts, categories, transactions, monthly balances | A transaction-only interface cannot carry dimensions, balances, or `no_data` months (ADR-007). |
| `gold_transaction_id` ("record/version") | `transaction_id` (stable across rebuilds) | Version identity belongs to issue #8. |
| `silver_transaction_id`, `classification_source`, `classification_version` on the fact | Moved to `GoldTransactionLineage` | Keep lineage away from report consumers. |
| `balance` | `balance_after` plus `balance_check`, `account_sequence` | Name the point in time. Publish the chain result and the order it was checked in. |
| `currency` on each transaction | `GoldAccount.currency` | Every amount is in its account's currency. |
| `reporting_month`, `created_at` on the fact | Removed | Month derives from `transaction_date`; build time is publication metadata (issue #8). |
| `counterparty` | Removed | No first-release source or measure uses it. It can return as a dimension through issue #7. |
| Refund = `adjustment` with a category | `refund` transaction type | Makes categorized reversals explicit, preserving signed netting for both category directions. `category_id` becomes required or null per type, with no conditional. |
| Coverage derived by analytics | Published by Gold on `MonthlyBalanceSnapshot` | Needs source-derived ordering and managed-period knowledge (ADR-007). |
| `boundary_transactions()` *(0.2 draft)* | Removed | Consumers fetched the links into and out of a period only to judge coverage themselves. Gold now publishes coverage, so nothing reads them (ADR-007). |
| `day_sequence` on the transaction *(0.2 draft)* | `account_sequence` | Ordering within a date is Silver's (ADR-009). Gold publishes one account-wide order instead, so a consumer never reconstructs it from two fields. |
| `category_direction` on the transaction *(0.2 draft)* | `GoldCategory.direction` | Direction is an attribute of the category. Copying it onto every fact row lets the two disagree. |
| `GoldAccount.active` *(0.2 draft)* | `closed_on`, alongside the new `display_name`, `account_type`, `ownership_scope`, and `currency` | A boolean cannot bound the managed period: a closed account would keep producing snapshot rows. The other attributes make the account a real dimension rather than a key with a flag. |

Silver identity and within-date order are defined by ADR-009. Coverage uses
the admitted export evidence from ADR-006, including verified quiet months.

## Open Decisions

- Whether bank-provided categories are retained as a separate Gold attribution
  or only as Silver provenance (issue #7).
- Transfer matching confidence, evidence in lineage, and the review workflow
  (issue #7).
- Publication selection, identity across materializations, and whether any
  dimension needs historical (Type 2) interpretation (issue #8).
