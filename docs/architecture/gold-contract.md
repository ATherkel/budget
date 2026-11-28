---
type: architecture
---
# Gold Data Contract

## Summary

- Gold, rebuilt from Silver, the registries and classification inputs, is
  what reports read: accounts, categories, transactions, allocations, balances.
- Analytics and forecasting read it only through the interface below, never
  Bronze or Silver; presentation and APIs read analytics reports.
- The only normative Gold schema, version `0.3`; a break needs a new version.
- The numbered [invariants](#invariants) hold in every publication and never
  renumber, because code and tests cite them.
- Lineage, where a fact came from, is for review tooling; a transaction's
  `classification` is the part of it reports may show.

| Topic | Owner |
| --- | --- |
| How a transaction gets its type and category | [`classification.md`](classification.md) |
| Publications, recipes, retention and reader lifetime | [`publications.md`](publications.md) |
| The model behind the schema: grains, balance chain, coverage, worked example | [`gold-layer.md`](gold-layer.md) |
| Evidence ranges | [`silver-layer.md`](silver-layer.md#evidence-ranges) |

## Shared Value Types

| Type | Values / shape | Meaning |
| --- | --- | --- |
| `ReportingMonth` | `YYYY-MM` | Calendar month. `ReportingMonth.of(d)` is derived solely from a `date`. |
| `AccountType` | `current`, `savings` | First-release account types. The account domain reserves further types; Gold rejects them until a reporting policy exists. |
| `OwnershipScope` | `household`, `person` | Scopes inside the reporting boundary. Accounts outside it are never Gold accounts. |
| `CategoryDirection` | `income`, `expense` | Which measure a category reports under. |
| `TransactionType` | `income`, `expense`, `refund`, `transfer`, `adjustment`, `unknown` | Household interpretation of a booked transaction. |
| `BalanceCheck` | `opening`, `consistent`, `break`, `missing_balance` | Result of the balance-chain check for one transaction. |
| `Classification` | `source`, `rule_ids`, `decision_id` | What decided one transaction's type; the fields mean what lineage's `classification_source`, `rule_ids` and `decision_id` mean. |
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
| `owner_id` | string | Yes | The `GoldOwner` the account belongs to. `legacy-unrecorded` on an account a publication stored before owners were recorded; a rebuild replaces it. |
| `currency` | ISO 4217 string | Yes | Currency of every amount and balance on this account. `DKK` in the first release. |
| `closed_on` | `date`/null | No | Date the account closed; null while open. Ends the account's managed period. |
| `coverage_start` | `date`/null | No | First day of the account's earliest [evidence range](silver-layer.md#evidence-ranges). Null when the account has no admitted import run. |
| `evidence_through` | `date`/null | No | Last day of the account's latest evidence range, never derived from an export date. Null when no export of the account has been imported. Days between the two dates can still fall in a gap between ranges. |

### `GoldOwner`

One row per owner the household declares in `accounts.toml`
([Owner](../CONTEXT.md#accounts-and-boundary)). Type 1. `GoldRepository.owners()`
returns them in display order.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `owner_id` | string | Yes | Durable, household-assigned identifier. |
| `display_name` | string | Yes | Household-facing name. |
| `display_order` | int | Yes | Position in the household's declaration, counting from 1. |

### `GoldCategory`

One row per assignable category, in exactly one group, which is never assigned
itself. Type 1: a rename or regroup restates history, so it is recorded in
[`category-changes.md`](../domains/category-changes.md) the day it is made.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `category_id` | string | Yes | Durable, household-assigned identifier. |
| `name` | string | Yes | Household-facing category name. |
| `group_id` | string | Yes | Durable identifier of the category group. |
| `group_name` | string | Yes | Household-facing category group name. |
| `direction` | `CategoryDirection` | Yes | `income` or `expense`. |

There is no calendar dimension: a `date` is its own key and `ReportingMonth`
derives from it. Persistence may add a calendar table without changing the
contract.

## Facts

### `GoldTransaction`

Grain: one booked transaction on one account. Amounts are signed: money in is
positive, money out negative. A transaction has no category of its own; that is
the allocation fact ([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `transaction_id` | string | Yes | The Silver canonical `transaction_id`, unchanged (ADR-009), so a rebuild yields the same value and every layer names a transaction by one identifier. |
| `account_id` | string | Yes | References `GoldAccount`. |
| `transaction_date` | `date` | Yes | Source transaction date (Danske: purchase date), exactly as supplied; the reporting month derives from it (ADR-009). |
| `account_sequence` | int | Yes | Position in the account's booked history, starting at 1, following `(transaction_date, day_sequence)` from Silver (ADR-009). Used only for ordering; it is not an identity and may shift when earlier transactions are imported. |
| `amount` | `Decimal` | Yes | Signed amount in the account's currency. |
| `description` | string | Yes | Normalized human-readable transaction text. |
| `transaction_type` | `TransactionType` | Yes | Household interpretation. |
| `transfer_group_id` | string/null | No | Shared by the two legs of a paired transfer, derived from their `transaction_id`s so it is stable across rebuilds. Null for a one-sided transfer and every other type. |
| `balance_after` | `Decimal`/null | No | Bank-stated balance from the latest admitted export covering this date (ADR-009). Null only for sources that state no balances, and for a row that states no balance in a balance-stating export admitted by *accept discrepancy* (ADR-016). Other inconsistent balance-stating exports are quarantined under ADR-010. |
| `balance_check` | `BalanceCheck` | Yes | Result of the [balance-chain check](gold-layer.md#balance-chain-evaluation) for this transaction. |
| `classification` | `Classification` | Yes | What decided `transaction_type`: the same `classification_source`, `rule_ids` and `decision_id` as its [lineage](#goldtransactionlineage), named `source`, `rule_ids` and `decision_id`. Rule and decision ids are household configuration, not source identifiers, so reports may show them. |

### `GoldCategoryAllocation`

Grain: one category allocation of one booked transaction, the only place a
category is assigned. In the first release a classified transaction has exactly
one, for its whole amount; more later needs no change to this grain or its
consumers. It repeats the transaction's account and date, so category reports
slice by account and month without a join.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `allocation_id` | string | Yes | Stable identifier, derived deterministically from `transaction_id` and `category_id`. A rebuild yields the same value, and so does re-dividing a split, which changes amounts rather than identities. |
| `transaction_id` | string | Yes | References `GoldTransaction`. |
| `account_id` | string | Yes | References `GoldAccount`; equals the transaction's. |
| `transaction_date` | `date` | Yes | Equals the transaction's; the reporting month derives from it. |
| `category_id` | string | Yes | References `GoldCategory`. |
| `amount` | `Decimal` | Yes | Signed share of the transaction's amount, in the account's currency. |

### `MonthlyBalanceSnapshot`

Grain: one account for one reporting month of its managed period, with exactly
one row per month, quiet months included. The managed period runs from the month of the account's first booked
transaction to the **latest published month**, the month of the latest
`evidence_through` over every `GoldAccount`, or to the month of `closed_on` if
earlier, so a future closing date adds no row. An account whose exports lag
still has a row for each later month, reported `partial` or `no_data`.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `account_id` | string | Yes | References `GoldAccount`. |
| `month` | `ReportingMonth` | Yes | The reporting month. |
| `opening_balance` | `Decimal`/null | No | Balance immediately before the month's first transaction: that transaction's `balance_after` minus its `amount`. |
| `closing_balance` | `Decimal`/null | No | `balance_after` of the month's last transaction by `account_sequence`, bank-stated only. |
| `coverage` | `Coverage` | Yes | Trust status for this account and month, as [`gold-layer.md`](gold-layer.md#coverage) defines it. |
| `late_bookings_settled` | bool | Yes | True when a counted export was produced late enough after the month's last day, and covers that day, for late bookings to have appeared. The rule is in [`gold-layer.md`](gold-layer.md#late-bookings-settled). Computed at build from recorded export dates and ranges, never from the clock. |

A complete quiet month carries the last stated balance into both. Both are
null when the needed balance is missing, the month is `no_data`, or it is quiet
and not `complete`.

Additivity: `amount` is additive across every dimension within one currency,
on each fact, but transactions and allocations are never summed together: they
describe the same money. Balances sum across accounts in one month, never
across months. `coverage` is non-additive.

## Invariants

1. Every `account_id` and `category_id` on a fact references a published
   dimension row. Every `GoldAccount` is inside the reporting boundary.
   Dimension keys (`account_id`, `category_id`, `group_id`) are immutable and
   never reused; a category or account is retired by deactivating it, never by
   repointing its key. Any other
   attribute may change and restates history (Type 1). A Silver transaction on
   an account the registry no longer declares refuses the build
   ([`accounts.toml`](operations.md#accountstoml)).
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
14. No `transaction_date` falls after its account's `closed_on`. The Gold
    build refuses a `closed_on` that would break this, rather than dropping
    the transactions after it
    ([`operations.md`, `accounts.toml`](operations.md#accountstoml)).
15. A consumer reads exactly one Gold publication at a time, the current one
    unless it opens another, and every record it reads belongs to it
    ([identity across publications](publications.md#identity-across-publications)).
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

Analytics, forecasting, APIs and presentation-facing services depend on this
protocol only, never on the persistence technology. Date and month ranges are
inclusive. `account_ids=None` means every account and an empty collection
none; a bare `str` raises `TypeError`, as a forgotten pair of brackets.

```python
class GoldRepository(Protocol):
    def publication(self) -> GoldPublication: ...

    def accounts(self) -> Sequence[GoldAccount]: ...

    def owners(self) -> Sequence[GoldOwner]: ...

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

Consumers may filter, join on dimension keys and aggregate, but never assume a
table name, source identifier or CSV column. A month with no snapshot row is
outside the account's managed period; a month beyond the latest published one
has no data and is never zero.

Gold supplies only `late_bookings_settled`; whether a period is provisional is
decided when a report is read
([`presentation-layer.md`](presentation-layer.md#data-trust-display)).

Household income and expenses are summed over `transactions`; category and
group spending over `category_allocations`. They agree because allocations sum
exactly to their transactions.

A `GoldRepository` reads from one publication. Consumers get one through
`GoldPublications`:

```python
class GoldPublications(Protocol):
    def current(self) -> GoldPublication | None: ...

    def available(self) -> Sequence[GoldPublication]: ...

    def open(self, publication_id: int) -> GoldRepository: ...
```

`available()` lists the retained publications: current, previous and labeled.
`current()` may return `None`, and `open()` raises
`PublicationUnavailableError`; when, and how long a `GoldStore` may live, is in
[`publications.md`](publications.md#reading-a-publication).

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

Lineage explains where a Gold fact came from, for review and audit tooling such
as the CLI's review and rebuild. Analytics and presentation never depend on it.

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
| `classification_version` | string | Yes | Fingerprint of the classification inputs: the configuration snapshot (account registry, taxonomy, and rules) and the effective classification decisions ([`publications.md`](publications.md)). The transfer matching policy and the classifier's code are not part of it; they change with the recipe's code version. |
| `transfer_evidence` | `TransferEvidence`/null | Conditional | Required on every `transfer`, otherwise null. |
| `review_item_ids` | list of string | Yes | Open classification review items involving this transaction. Often empty. |
| `bank_category` | string/null | Optional | The bank's category label, retained as privileged provenance for rule explanation and review. It never becomes a Gold Category. Null means the source supplied none or an older publication did not retain it. |
| `adjustment_reason` | string/null | Conditional | The explanation invariant 3 asks of an adjustment: the reason its rule or decision gives. Required on every `adjustment`, otherwise null. |

The classification fields describe the transaction as a whole; per-allocation
provenance comes with the split workflow.

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
while its cause does, and stores them atomically with the result. The review
reader selects the current publication in one SQLite read snapshot, outside
the analytics interface. A non-applicable decision stays findable by its
decision and surviving targets; a missing target is not reconstructed. Silver's
import review items are separate.

Each publication's [recipe](publications.md#the-recipe) is privileged metadata
too, for the CLI and audit tooling.

## Contract Fixtures

Synthetic fixtures cover every transaction type, allocation rule, balance
check and coverage case above, a closed account and two categories in one
group; the worked example in [`gold-layer.md`](gold-layer.md#worked-example-synthetic)
covers most. Classification fixtures reproduce every scenario and taxonomy
change in [`classification.md`](classification.md) exactly. Publication
fixtures reproduce the scenarios in
[`publications.md`](publications.md#synthetic-scenarios), including an
unchanged result fingerprint after a full rebuild.
