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
rebuilt when classification logic changes. The classification policy is in
[`classification.md`](classification.md). Each build is a publication, built
from a recorded recipe, and a consumer reads exactly one publication
([`publications.md`](publications.md),
[ADR-014](../decisions/ADR-014-gold-publications-and-history.md)).

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
| `OwnershipScope` | `household`, `person` | Scopes inside the reporting boundary. Accounts outside it are never Gold accounts. |
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
never assigned to transactions. All categories in a group share one direction.
Type 1: renaming or regrouping a category restates all history, so each such
change is recorded in
[`category-changes.md`](../domains/category-changes.md) on the day it is
made.

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

Grain: one booked transaction on one account. Amounts are signed in the
account's currency: money into the account is positive and money out is
negative. A transaction carries no category of its own; category assignment
is a separate fact at its own grain
([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `transaction_id` | string | Yes | Stable identifier, derived deterministically from the Silver canonical transaction identity, so a rebuild yields the same value. |
| `account_id` | string | Yes | References `GoldAccount`. |
| `transaction_date` | `date` | Yes | Source transaction date (Danske: purchase date), exactly as supplied; the reporting month derives from it (ADR-009). |
| `account_sequence` | int | Yes | Position in the account's booked history, starting at 1, following `(transaction_date, day_sequence)` from Silver (ADR-009). Used only for ordering; it is not an identity and may shift when earlier transactions are imported. |
| `amount` | `Decimal` | Yes | Signed amount in the account's currency. |
| `description` | string | Yes | Normalized human-readable transaction text. |
| `transaction_type` | `TransactionType` | Yes | Household interpretation. |
| `transfer_group_id` | string/null | No | Shared by the two legs of a paired transfer, derived from their `transaction_id`s so it is stable across rebuilds. Null for a one-sided transfer and every other type. |
| `balance_after` | `Decimal`/null | No | Bank-stated balance from the latest admitted export covering this date (ADR-009). Null only for sources that state no balances; inconsistent balance-stating exports are quarantined under ADR-010. |
| `balance_check` | `BalanceCheck` | Yes | Result of the balance-chain check for this transaction (see `gold-layer.md`). |

### `GoldCategoryAllocation`

Grain: one category allocation of one booked transaction
([ADR-008](../decisions/ADR-008-category-allocation-grain.md)). This is the
only place a category is assigned. In the first release a classified
transaction has exactly one allocation, for its whole amount; authoring more
than one is a later release, and needs no change to this grain or to any
consumer that already reads it.

The allocation repeats its transaction's account and date so that category
reporting slices by account and month without joining the transaction fact.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `allocation_id` | string | Yes | Stable identifier, derived deterministically from `transaction_id` and `category_id`. A rebuild yields the same value, and so does re-dividing a split, which changes amounts rather than identities. |
| `transaction_id` | string | Yes | References `GoldTransaction`. |
| `account_id` | string | Yes | References `GoldAccount`; equals the transaction's. |
| `transaction_date` | `date` | Yes | Equals the transaction's; the reporting month derives from it. |
| `category_id` | string | Yes | References `GoldCategory`. |
| `amount` | `Decimal` | Yes | Signed share of the transaction's amount, in the account's currency. |

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

Additivity: `amount` is additive across every dimension within one currency,
on both the transaction and the allocation fact. The two are never summed
together: a transaction and its allocations describe the same money, so adding
them double-counts it. Balances are semi-additive: they may be summed across
accounts for the same month, never across months. `coverage` is non-additive.

## Invariants

1. Every `account_id` and `category_id` on a fact references a published
   dimension row. Every `GoldAccount` is inside the reporting boundary.
   Dimension keys — `account_id`, `category_id`, and `group_id` — are
   immutable and are never reused for a different meaning. A category or
   account is retired by deactivating it, never by repointing its key. Every
   other attribute may change, and changing one restates history, which is
   what Type 1 means.
2. Each booked Silver transaction on a Gold account yields exactly one
   `GoldTransaction`. Only `booking_status=booked` rows qualify; pending and
   cancelled records remain provenance.
3. Sign convention: `expense` amounts are negative; `income` amounts are
   positive. A `refund` reverses the direction of the category it is allocated
   to: positive for an expense category, negative for an income category.
   `adjustment` may take either sign and needs an explanation.
4. A classified transaction — `income`, `expense`, or `refund` — has at least
   one `GoldCategoryAllocation`. A `transfer`, `adjustment`, or `unknown`
   transaction has none. In the first release a classified transaction has
   exactly one, whose `amount` equals the transaction's `amount`
   ([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).
5. A transaction's allocations sum exactly to its `amount`. No remainder is
   left unallocated and no rounding tolerance is permitted. Each allocation's
   `amount` is non-zero and carries the same sign as the transaction's, so a
   share of a purchase can never read as a refund.
6. A transaction has at most one allocation per category, so `allocation_id`
   is unique. An allocation's `account_id` and `transaction_date` equal its
   transaction's.
7. An allocation's category direction matches its transaction's type:
   `income` → an `income` category, `expense` → an `expense` category; a
   `refund` allocation carries the category of the movement it reverses.
8. A `transfer` is excluded from income, expense, savings-rate, and category
   spending totals. It remains visible in account activity.
9. `transaction_date` is used exactly as supplied by the source. No timezone
   conversion is applied at any layer.
10. Per account, `account_sequence` runs 1, 2, 3, … without gaps, and
    `transaction_date` never decreases as `account_sequence` increases.
11. `balance_check` follows the balance-chain rules in `gold-layer.md`. A
    break or missing balance is never corrected or hidden.
12. `MonthlyBalanceSnapshot` has exactly one row per account per month of the
    managed period. When a row's `coverage` is `complete`,
    `opening_balance + sum(amounts in the month) == closing_balance`.
13. All first-release accounts use `DKK`. Consumers must never aggregate
    amounts or balances across different currencies.
14. No `transaction_date` falls after its account's `closed_on`.
15. A consumer reads exactly one Gold publication at a time, and every record
    it reads belongs to that publication. A consumer reads the current
    publication unless it opens another one explicitly. Identity across
    publications is defined in [`publications.md`](publications.md).
16. `transfer_group_id` is non-null only on `transfer` transactions. Each
    non-null value appears on exactly two transactions, which are on different
    accounts and whose amounts sum to zero.
17. A `transfer` with a null `transfer_group_id` is a one-sided transfer from a
    manual decision. Its lineage names a counterpart Gold account whose managed
    period does not include the transaction date.
18. All categories in a category group share one direction.
19. Every classification traces through lineage to its source: a manual
    decision, a transfer match, or a rule. `unknown` traces to none, and every
    `unknown` transaction has at least one open classification review item.

## Consumer Interface

Analytics, forecasting, APIs, and presentation-facing services depend on this
protocol only. The persistence technology is not part of this contract.
All date and month ranges are inclusive.

```python
class GoldRepository(Protocol):
    def publication(self) -> GoldPublication: ...

    def accounts(self) -> Sequence[GoldAccount]: ...

    def categories(self) -> Sequence[GoldCategory]: ...

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldTransaction]: ...

    def category_allocations(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldCategoryAllocation]: ...

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

Anything reported by category is summed over `category_allocations`, and
anything reported per transaction over `transactions`. Household income and
expenses are transaction measures; category and category-group spending are
allocation measures. Because allocations sum exactly to their transactions,
the two agree today and keep agreeing once a transaction carries several
allocations.

A `GoldRepository` is bound to one publication, and every method reads from
it. Consumers obtain one through `GoldPublications`:

```python
class GoldPublications(Protocol):
    def current(self) -> GoldPublication | None: ...

    def available(self) -> Sequence[GoldPublication]: ...

    def open(self, publication_id: int) -> GoldRepository: ...
```

`available()` lists the publications whose results are retained: the current
one, the previous one, and every labeled one. `current()` returns `None` when
there is no current publication: before a store's first successful build, and
between a Gold migration that could not convert the current result and the
build that follows it. `open()` raises `PublicationUnavailable`
when the publication does not exist or its result is not retained, including
one deleted after a consumer last opened it.

#### `GoldPublication`

Publication metadata. None of it enters the result fingerprint.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `publication_id` | int | Yes | Increasing per store. |
| `kind` | enum | Yes | `pipeline` for a build that became current when it was built, or `as_known_at` for a view, which is never current. |
| `label` | string/null | No | Household-assigned name. A labeled publication's result is retained. |
| `known_at` | datetime | Yes | The moment whose knowledge the publication represents: `built_at` for `pipeline`, and the requested cutoff for `as_known_at`. Past views take the provisional label as of this moment. A replay keeps the original value. |
| `built_at` | datetime | Yes | When the original build finished. A replay keeps the original value. Metadata only. |
| `replayed_at` | datetime/null | No | When the result was last re-created from its recipe; null if it never was. |
| `contract_version` | string | Yes | Gold contract version the publication implements. |
| `fingerprint_scheme` | string | Yes | Version of the canonical serialization the fingerprint is computed over. |
| `result_fingerprint` | string | Yes | SHA-256 over the canonical serialization of every consumer and lineage record. Under one `fingerprint_scheme`, equal fingerprints mean identical results; across schemes they are not comparable. |

## Lineage Interface (privileged)

Lineage explains where a Gold fact came from. Review and audit tooling reads it,
for example the CLI classification-review and rebuild workflows (issues #7 and
#10). Analytics and presentation must not depend on it.

```python
class GoldLineageRepository(Protocol):
    def transaction_lineage(
        self, transaction_ids: Collection[str]
    ) -> Sequence[GoldTransactionLineage]: ...

    def classification_review_items(self) -> Sequence[ClassificationReviewItem]: ...
```

#### `GoldTransactionLineage`

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `transaction_id` | string | Yes | The Gold transaction explained. |
| `silver_transaction_id` | string | Yes | Traceable parent Silver record, and through it the retained Bronze provenance, including the bank's category labels. |
| `classification_source` | enum | Yes | `manual`, `transfer_match`, `rule`, or `unclassified`. |
| `rule_ids` | list of string | Yes | The highest-priority matching rules; they decided only when `classification_source` is `rule`. Empty when no rule matched. |
| `decision_id` | string/null | Conditional | The manual decision that decided. Required when `classification_source` is `manual`, otherwise null. |
| `classification_version` | string | Yes | Fingerprint of the classification inputs: the configuration snapshot (account registry, taxonomy, rules, and matching policy) and the effective classification decisions ([`publications.md`](publications.md)). |
| `transfer_evidence` | `TransferEvidence`/null | Conditional | Required on every `transfer`, otherwise null. |
| `review_item_ids` | list of string | Yes | Open classification review items involving this transaction. Often empty. |

The classification fields describe how the transaction's type and its
allocations were derived. While a classified transaction has exactly one
allocation, one row per transaction says everything there is to say. Authoring
several allocations means one of them can be derived differently from another,
so per-allocation provenance is added to lineage with the split workflow; the
fields above keep their meaning for the transaction as a whole.

#### `TransferEvidence`

Confidence is a named evidence basis, not a score.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `basis` | enum | Yes | `same_day`, `date_gap`, `repeated_legs`, `manual_pair`, or `one_sided`. |
| `counterpart_account_id` | string | Yes | The other leg's Gold account. |
| `counterpart_transaction_id` | string/null | Conditional | The other leg. Null only for `one_sided`. |
| `date_gap_days` | int/null | Conditional | Days between the two transaction dates. Null only for `one_sided`. |
| `claim_rule_ids` | list of string | Yes | Rules that claim either leg as a transfer. Non-empty for every automatic pair. |

#### `ClassificationReviewItem`

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `review_item_id` | string | Yes | Derived from the kind and the identifiers involved, so it is stable across rebuilds. |
| `kind` | enum | Yes | `unclassified`, `rule-conflict`, `sign-mismatch`, `ambiguous-transfer`, `unmatched-transfer`, or `decision-not-applicable`. |
| `transaction_ids` | list of string | Yes | Transactions involved. Empty only when a decision's target is missing. |
| `rule_ids` | list of string | Yes | Rules involved, such as the conflicting rules. |
| `decision_id` | string/null | Conditional | The decision, for `decision-not-applicable`. |
| `reason` | string/null | No | Detail, such as `counterpart-may-not-be-imported`, `no-candidate`, or `target-missing`. |

Gold derives review items afresh on every build, so an item exists exactly
while its cause does. Silver's import review items (issue #5) are separate.

Each publication's recipe (its import runs, configuration snapshot,
decision-log position, and code version) is privileged metadata for the CLI
and audit tooling, alongside lineage. Its shape belongs to issue #10.

## Contract Fixtures

Before analytics or UI work begins, provide synthetic fixtures covering:
income; expense; refund netting against its category; adjustment without a
category; paired transfer; unmatched transfer candidate; unknown transaction;
a classified transaction and its single allocation summing to its amount; a
transaction type that must carry no allocation; manual classification decision
(visible through lineage); missing balance; chain break that demotes the
previous month; first managed month (`partial`); complete quiet month; partial
quiet month crossed by a broken link; `no_data` month beyond evidence; closed
account; and two categories sharing a group. The worked example in
`gold-layer.md` covers most of these.

Classification fixtures reproduce every synthetic scenario and taxonomy change
in [`classification.md`](classification.md) exactly. Publication fixtures
reproduce the lifecycle and view scenarios in
[`publications.md`](publications.md), including an unchanged result
fingerprint after a full rebuild.

## Changes in 0.2

This table covers everything 0.2 changes since 0.1. Rows marked *(0.2 draft)*
were introduced by the earlier 0.2 draft and are superseded here, so a reader
migrating from either version finds the whole path in one place.

| 0.1 or the earlier 0.2 draft | 0.2 | Why |
| --- | --- | --- |
| `GoldTransactionRepository.list_transactions` | `GoldRepository` with accounts, categories, transactions, category allocations, monthly balances | A transaction-only interface cannot carry dimensions, balances, or `no_data` months (ADR-007). |
| `gold_transaction_id` ("record/version") | `transaction_id` (stable across rebuilds) | One version of one fact is (`publication_id`, `transaction_id`) (ADR-014). |
| `silver_transaction_id`, `classification_source`, `classification_version` on the fact | Moved to `GoldTransactionLineage` | Keep lineage away from report consumers. |
| `balance` | `balance_after` plus `balance_check`, `account_sequence` | Name the point in time. Publish the chain result and the order it was checked in. |
| `currency` on each transaction | `GoldAccount.currency` | Every amount is in its account's currency. |
| `reporting_month`, `created_at` on the fact | Removed | Month derives from `transaction_date`; build time is `GoldPublication.built_at` (ADR-014). |
| No way to choose a publication | `GoldPublications`, `GoldPublication`, and `GoldRepository.publication()` | A consumer must read exactly one publication, and must be able to open a past one explicitly (ADR-014). |
| `counterparty` | Removed | Classification rules match description text instead; a counterparty dimension would be a later contract version. |
| Refund = `adjustment` with a category | `refund` transaction type | Makes categorized reversals explicit, preserving signed netting for both category directions. Whether a transaction has a category follows from its type, with no conditional. |
| Coverage derived by analytics | Published by Gold on `MonthlyBalanceSnapshot` | Needs source-derived ordering and managed-period knowledge (ADR-007). |
| `category_id` on the transaction | `GoldCategoryAllocation`, a fact at the grain of one category allocation of one transaction | Category assignment is its own grain. Writing it this way now means splitting a transaction later changes no grain, no interface, and no consumer query (ADR-008). |
| `classification_source` value `imported` | Removed; `transfer_match` added | Bank categories never classify on their own (ADR-011). |
| No transfer evidence or review items | `TransferEvidence`, `rule_ids`, `decision_id`, and `classification_review_items` in lineage | Transfers need auditable evidence, and the CLI review workflow needs a stable source (ADR-011, ADR-012). |
| `boundary_transactions()` *(0.2 draft)* | Removed | Consumers fetched the links into and out of a period only to judge coverage themselves. Gold now publishes coverage, so nothing reads them (ADR-007). |
| `day_sequence` on the transaction *(0.2 draft)* | `account_sequence` | Ordering within a date is Silver's (ADR-009). Gold publishes one account-wide order instead, so a consumer never reconstructs it from two fields. |
| `category_direction` on the transaction *(0.2 draft)* | `GoldCategory.direction` | Direction is an attribute of the category. Copying it onto every fact row lets the two disagree. |
| `GoldAccount.active` *(0.2 draft)* | `closed_on`, alongside the new `display_name`, `account_type`, `ownership_scope`, and `currency` | A boolean cannot bound the managed period: a closed account would keep producing snapshot rows. The other attributes make the account a real dimension rather than a key with a flag. |

Silver identity and within-date order are defined by ADR-009. Coverage uses
the admitted export evidence from ADR-006, including verified quiet months.

## Open Decisions

- File formats for rules and manual decisions, and the CLI review commands
  (issue #10).
- Whether money moved to savings, investment, or loan accounts that are not
  imported should count differently in the savings measure; it is an expense
  today (issue #12).
