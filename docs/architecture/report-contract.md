---
type: architecture
---
# Report Contract

## Summary

- The only schema, version `0.3`, of the reports [analytics](analytics-layer.md)
  builds as `HouseholdReports` and [presentation](presentation-layer.md) shows.
- Analytics owns every figure and judgement; presentation only formats, never
  summing or opening Gold.
- A page pins one publication and one reference date, never mixing two.
- A figure with no evidence is null, never zero, and a failure raises an error,
  never an empty report.
- [Open questions](https://github.com/ATherkel/budget/issues?q=is%3Aissue+is%3Aopen+%22report-contract.md%22).

## Value Types

| Type | Values / shape | Meaning |
| --- | --- | --- |
| `ReportingMonth` | `YYYY-MM` | As in [`gold-contract.md`](gold-contract.md#shared-value-types). |
| Money | `Decimal` | Exact amount in the report's currency, at that currency's minor units (DKK: two places). Never a float. |
| Ratio | `Decimal` | The unrounded quotient, computed in Python's default decimal context: 28 significant digits, rounded half-even. Rounding for display belongs to presentation. |
| `Coverage` | `complete`, `partial`, `no_data` | As in [`gold-contract.md`](gold-contract.md#shared-value-types). |
| `AccountMonthStatus` | `partial`, `no_data`, `outside_history` | Status of one selected account in one month that is not `complete`; see [Coverage](#coverage). |

Serialized, money is a decimal string with exactly the currency's minor-unit places
(`"-450.00"`), a ratio its `Decimal`'s string (`"0.6392"`), a month
`"YYYY-MM"` and a date ISO 8601; money and ratios are never JSON numbers.

Signs: Income, Expenses and category spending are positive, and negative only
under a net Refund. Net cash flow is negative when Expenses exceed Income. On
the Unclassified and Adjustment lines, money in is ≥ 0 and money out ≤ 0.

## Interface

```python
class HouseholdReports(Protocol):
    def current_publication(self) -> ReportPublication: ...

    def selection_options(
        self, publication_id: int, reference_date: date
    ) -> SelectionOptions: ...

    def monthly_overview(self, context: ReportContext) -> MonthlyOverview: ...

    def spending_detail(
        self, context: ReportContext, subject: DetailSubject, scope: DetailScope
    ) -> SpendingDetail: ...

    def diagnostics(self, context: ReportContext) -> Diagnostics: ...

    def account_activity(self, context: ReportContext) -> AccountActivity: ...
```

`current_publication()` raises `NothingPublished` when Gold has no current
publication. `selection_options()` and every context-addressed report raise
`PublicationUnavailableError` when the named result is not retained.
Context-addressed reports raise `InvalidSelection` for a context breaking a
[`ReportContext`](#reportcontext) rule or, for detail, a subject breaking the
[`SpendingDetail`](#spendingdetail) one. A failure is never an empty or zero
report. In code each name ends in `Error`
(`NothingPublishedError`, `InvalidSelectionError`), as the lint rules require.

### `ReportContext`

The one selection every report on a page shares.

| Field | Type | Meaning |
| --- | --- | --- |
| `publication_id` | int | The publication every report on the page reads. |
| `account_ids` | set of string | The selected accounts. Any non-empty combination, regardless of ownership. |
| `month` | `ReportingMonth` | The selected month. A report covering several months will take its range as its own parameter, anchored to this month. |
| `reference_date` | `date` | The date the provisional rule is judged on. Analytics never reads a clock. |

A page resolves its context once, from the current publication and today in
Europe/Copenhagen, and every follow-up request carries the same
`publication_id` and `reference_date`. The pin travels in the page's address,
so reload, back and forward keep it; opening the page without one resolves a
fresh context, selecting every account and the reference date's month.

A context is valid when:

1. `account_ids` is non-empty;
2. every account ID names a `GoldAccount` of the publication;
3. every selected account has the same currency (Gold contract invariant 13:
   amounts in different currencies are never aggregated);
4. `month` lies from `SelectionOptions.first_month` through
   `SelectionOptions.last_month`, inclusive.

Otherwise `monthly_overview()` raises `InvalidSelection`, whose `reasons` holds
every rule broken: `no_accounts`, `unknown_account`, `mixed_currencies`, or
`month_out_of_range`. `unknown_account` also lists the IDs. The valid months
do not depend on which accounts are selected, so changing the account
selection never invalidates the month.

### `SelectionOptions`

What a page may select within one publication on one reference date.

| Field | Type | Meaning |
| --- | --- | --- |
| `publication` | `ReportPublication` | The publication the options belong to. |
| `accounts` | list of `SelectableAccount` | Every `GoldAccount` in the publication, ordered by `account_id`: `account_id`, `display_name`, `account_type`, `owner_id`, `currency`. Every Gold account is inside the Reporting boundary, so this is "all imported accounts". |
| `owners` | list of `SelectableOwner` | Every `GoldOwner` in the publication, in display order: `owner_id`, `display_name`. A page selects an owner as the set of accounts naming it. A publication stored before owners were recorded has none, and its accounts name `legacy-unrecorded` ([`gold-contract.md`](gold-contract.md#goldaccount)) until the next rebuild. |
| `first_month` | `ReportingMonth` | The earliest month in which any account has a `MonthlyBalanceSnapshot` row. The month of the reference date when no account has one yet. |
| `last_month` | `ReportingMonth` | The month of the reference date. |

### `ReportPublication`

| Field | Type | Meaning |
| --- | --- | --- |
| `publication_id` | int | As on `GoldPublication`. |
| `kind` | `pipeline`, `as_known_at` | As on `GoldPublication`. |
| `label` | string/null | As on `GoldPublication`. |
| `known_at` | datetime | As on `GoldPublication`. |
| `is_current` | bool | Whether this publication was current when the report was read. |

A pinned page keeps reading its publication after a newer build, while the
result is retained; `is_current` turns false, so the page can offer the newer
figures. Once the result is deleted, the next read raises
`PublicationUnavailableError`, and the page offers the current publication
rather than substituting it.

### `MonthlyOverview`

| Field | Type | Meaning |
| --- | --- | --- |
| `context` | `ReportContext` | The context the report answers, echoed so a response can be matched to the selection that asked for it ([response eligibility](#navigation-and-selection-transitions)). |
| `publication` | `ReportPublication` | The publication read. |
| `currency` | ISO 4217 string | The selected accounts' shared currency. |
| `income` | Money/null | **Income** in [`analytics-layer.md`](analytics-layer.md#initial-measures): income transactions plus income-direction Refunds. |
| `expenses` | Money/null | **Expenses** in `analytics-layer.md`: expense transactions plus expense-direction Refunds, reported positive. |
| `net_cash_flow` | Money/null | Income − Expenses: the money left after all expenses. It equals Savings in this release. |
| `savings_rate` | Ratio/null | `net_cash_flow / income`, which equals `savings / income` while the two are equal. Null when `income` is null or not positive. |
| `categories` | list of `CategorySpending` | One row per expense-direction Category with at least one allocation in the month, ordered by `spending`, largest first, and then by `category_id`. Empty when `coverage.status` is `no_data`. |
| `unclassified` | `MoneyInOut`/null | Unclassified money: `unknown` transactions. |
| `adjustments` | `MoneyInOut`/null | `adjustment` transactions, which carry no allocation. |
| `coverage` | `ReportCoverage` | Coverage of every figure above. |
| `provisional` | `Provisional`/null | Why the month is provisional; null when it is not. |

`income`, `expenses`, `net_cash_flow`, `unclassified` and `adjustments` are
null exactly when `coverage.status` is `no_data`: with no evidence, a figure is
unknown, never zero. A `partial` report carries the known amounts, shown only
with its coverage.

Income and Expenses sum transactions, category spending sums allocations
(ADR-008), so categories always add up to Expenses. Transfers are excluded from
every figure whichever accounts are selected (Gold invariant 8). An absent
Category is a known zero only when coverage is `complete`.

`CategorySpending`: `category_id`, `name`, `group_id`, `group_name`, and
`spending`, the Category's net spending as Money: −(Σ allocations of `expense`
transactions + Σ allocations of `refund` transactions), negative when Refunds
exceed purchases. The overview carries no Category group totals and no
transaction rows; reports that need them add them.

Enkel shows every row in the given order, neither reordered nor truncated, so
the list adds up to Expenses with no remainder line; a net Refund Category
falls to the bottom.

`MoneyInOut`: `money_in` (Σ positive amounts), `money_out` (Σ negative
amounts) and `count`, never netted, so offsetting entries cannot read as
nothing.

Unclassified money is a trust condition of its own: money left leaves it out
and may be off by up to that amount. When `unclassified.count` > 0, Enkel says
so quietly, linking to the [explanation](#navigation-and-selection-transitions).
Enkel always shows a fourth summary figure, Ukategoriseret: `money_in` as Ind,
with a plus sign when positive, and `money_out` as Ud with its minus sign. A
known zero reads 0,00 kr. and a null reads as unknown. The count belongs to
Kontrol; the explanation shows neither amounts nor count. Adjustments carry no
note.

### Coverage

`ReportCoverage` holds `status` (`Coverage`) and `account_months`, a list of
`AccountMonthCoverage`: `account_id`, `display_name`, `month`, and `status`
(`AccountMonthStatus`). It lists every selected account-month that is not
`complete`, ordered by `account_id` and then `month`.

Each selected account-month gets one status:

- **Its `MonthlyBalanceSnapshot` row's `coverage`**, when the row exists.
- **`outside_history`**, when the account has a managed period and the month
  lies before its first month or after the month it closed. The month is
  outside the account's reported history (`CONTEXT.md`, *Managed period*), so
  no evidence can ever be missing for it.
- **`no_data`**, otherwise: the account has no managed period yet (it was never
  imported, or has no booked transaction), or the month is after the latest
  published month.

The contributing account-months are the selected ones not `outside_history`.
`status` is `complete` when all of them are, `no_data` when none has evidence
(or none contributes), and `partial` otherwise. One status covers every figure,
since all draw on the same account-months.

### `Provisional`

`Provisional` holds `reasons`, a set of `current_month` and
`late_bookings_unsettled`, and `unsettled`, the account-months behind the
second reason (`account_id`, `display_name`, `month`), ordered as in
`ReportCoverage`. It applies the rule in
[`presentation-layer.md`](presentation-layer.md#data-trust-display):

- `current_month` when `month` is the month of `reference_date`;
- `late_bookings_unsettled` when a contributing account-month whose account
  has a managed period is not settled: its snapshot row has
  `late_bookings_settled` false, or it has no row because the month is after
  the latest published month.

An account without a managed period never holds the label, even one imported
without a booked transaction, and neither does an `outside_history` month.

### Diagnostics

`diagnostics()` follows the overview's [money](#monthlyoverview),
[Coverage](#coverage) and [Provisional](#provisional) rules. `evidence` exposes
selected accounts' [`evidence_through`](gold-contract.md#goldaccount) directly,
including null. Transfer counts count selected legs, not pairs.

For each selected account-month:

```text
internal_residual = closing_balance - (opening_balance + income_minus_expenses
    + transfers + unclassified_in + unclassified_out + adjustments_in + adjustments_out)
opening_gap = opening_balance - previous_closing_balance
```

Either result is unknown if any of its inputs is missing. Arithmetic agreement
never upgrades Coverage: the synthetic March example has internal residual
`0.00`, opening gap `-500.00` and Coverage `partial`.

### `SpendingDetail`

The entries behind one Category's or group's figure on the overview, for the
selected month or the year to date.

`DetailSubject` is `kind` (`category` or `group`) and `id`. It must name an
expense Category, or a group holding one; otherwise `InvalidSelection` adds
`unknown_category` to any [`ReportContext`](#reportcontext) rule broken.
`DetailScope` is `month` or `year_to_date`: January through the selected
month.

| Field | Type | Meaning |
| --- | --- | --- |
| `context`, `subject`, `scope` | | Echoed, as on `MonthlyOverview`. |
| `publication`, `currency` | | As on `MonthlyOverview`. |
| `name`, `group_id`, `group_name` | string | The subject's name and group; a group is its own. |
| `first_month`, `last_month` | `ReportingMonth` | The scope's months. |
| `spending` | Money/null | Net spending over the scope, as `CategorySpending.spending`. Null exactly when coverage is `no_data`. |
| `rows` | list of `SpendingDetailRow` | One per allocation of the subject in the scope; empty when coverage is `no_data`. |
| `coverage` | `ReportCoverage` | [Coverage](#coverage), over every selected account-month in the scope. |
| `provisional` | `Provisional`/null | [`Provisional`](#provisional), with `late_bookings_unsettled` over every month in the scope. |

`SpendingDetailRow`: `transaction_date`, `description`, `account_id`,
`account_display_name`, `category_id`, `category_name`, and `spending`, the
allocation's amount with its sign flipped, so a Refund is negative. Newest
first: by date, then `account_id`, then booking sequence, descending. A row
carries no other identifier.

The rows add up to `spending`, and `spending` equals the overview: for
`month`, the Category's row (0.00 when absent) or the sum of the group's rows;
for `year_to_date`, the sum of the months. Transfers, Adjustments and
Unclassified money have no allocation, so they never appear.

## Navigation and Selection Transitions

The interaction a page owes its reader. It is route-neutral: it constrains what
the reader is shown, never the transport or URL shape, and the report DTOs
carry no HTML, URL or framework schema.

For screen ownership and mode navigation, see the
[“Enkel” and “Avanceret” display contract](presentation-layer.md#enkel-and-avanceret).

**One pinned context.** A page pins `publication_id` and the Copenhagen
`reference_date` for the whole visit ([`ReportContext`](#reportcontext)).
Navigation inside the page (an account or month change, a fragment, a
drill-down, a mode change, a link or a form) keeps the pin and never
re-resolves it. Only an explicit refresh or return to the current publication
resolves a fresh context; in the dashboard both open the page without a pin,
as the "newer figures" link does.

**Central validation.** Every candidate selection, restored or entered, is
validated against its pinned publication by the [`ReportContext`](#reportcontext)
rules before use. Validation never resolves the current publication and never
repairs a selection silently.

**Response eligibility.** A successful response renders only when:

1. it answers the activity that is current now: the navigation change or
   request generation that asked for it is still the active one; and
2. its echoed `context` equals the active validated selection on all four
   fields, with `account_ids` compared canonically as a set.

Anything else is discarded, so a selection change invalidates every
outstanding response for the previous one, and figures can never appear under
another selection's controls. Returning to an earlier selection is a new
request: `A -> B -> A` does not revive the first `A`'s response.

**Failures.** A failure carries no report or echoed context, so it is matched
to the active request generation and its candidate selection, never given an
invented `ReportContext`. One for the current generation displays:
`InvalidSelection` names the broken rules, `NothingPublished` says nothing is
published, `PublicationUnavailableError` offers the current publication. One
for a superseded generation is discarded, so a late error never replaces a
newer success.

**Empty selection.** No accounts selected is a prompt, not a report:
presentation invalidates outstanding responses, clears the previous figures,
keeps the account controls usable, and lets no late response repaint. A
request actually made for it still raises `InvalidSelection` with
`no_accounts`.

**Back and forward.** A history entry carries its full state: the pinned
`publication_id`, `reference_date`, selection and mode. Going back or forward
restores it even after a refresh resolved another context, validates it
against its own publication, and reads again under a fresh generation. An
unretained result stays `PublicationUnavailableError`, a broken selection
`InvalidSelection`, an empty one the prompt; nothing falls back to the current
publication, the default selection or the previous view. Links and forms keep
the pin the same way.

**Explanation of coverage, provisional figures and Unclassified money.** It is
reachable within the pinned context, without the Kontrol screen: the report's
incomplete account-months, provisional reasons, and whether it has
Unclassified money. Analytics owns the judgements; presentation owns the
destination.

**Report figures and browser storage.** Navigation state and browser storage
hold only the pinned identity and the selection, never a financial payload or
a new financial model
([`presentation-layer.md`](presentation-layer.md#non-responsibilities)). This
governs what is stored and reused, not what the rendered page displays.

### Account Activity

`account_activity()` returns the selected month's Booked transactions and the
selected accounts' balance evidence under the same pinned context,
[Coverage](#coverage) and [Provisional](#provisional) rules as the overview.
Rows preserve the published date, description, signed amount and transaction
type, newest first by date, account ID and account sequence.

Each `AccountActivitySnapshot` carries `money_in_out`: a [`MoneyInOut`](#monthlyoverview)
over every selected movement for that account, regardless of transaction type.
Its `money_in` is the sum of positive amounts and `money_out` the sum of
negative amounts; a zero amount contributes to neither. Transfers, Refunds,
Adjustments and Unclassified movements therefore contribute by sign here,
without changing the household Income and Expenses measures. `money_in_out`
is null exactly when the account's Coverage is `no_data`; an `outside_history`
month is a known zero because it cannot be missing evidence. A `partial`
account keeps the known totals and its separate Coverage warning.

A dated balance is the account month's last transaction's
[`balance_after`](gold-contract.md#goldtransaction), ordered by
`account_sequence`. It is not the month-end balance. Monthly opening and
closing balances remain the separate [published snapshot](gold-contract.md#monthlybalancesnapshot)
values. A final null balance stays null, and an older observation may appear
only with its own date. A quiet partial month can therefore have unknown
snapshot balances, while a quiet complete month may carry only an earlier
dated observation. Observations from different dates are not summed into a
household bank balance.

Transfers keep Gold's published classification
([`GoldTransaction`](gold-contract.md#goldtransaction),
[matching](classification.md#transfer-matching)). Two legs with the same
`transfer_group_id` are publicly paired, including when the other leg is
outside the selected account or month; that other leg is evidence, never an
extra activity row. A Transfer without a group is one-sided. Unknown
descriptions stay unknown text, and an unknown transaction is never inferred
to be a Transfer. Matching evidence and decisions remain private lineage.

The selected account carries [`GoldAccount.evidence_through`](gold-contract.md#goldaccount)
directly, including null and gaps between Evidence ranges. It is not inferred
from a transaction, export date or Coverage status.

## Worked Examples (synthetic)

All examples read the publication of the worked example in
[`gold-layer.md`](gold-layer.md#worked-example-synthetic), call it P1, with
both of its accounts selected unless stated. Its latest published month is
2026-05, every snapshot row through April has `late_bookings_settled` true,
and the May rows have it false. The reference date is 2026-05-14 unless
stated, so `SelectionOptions` has `first_month` 2026-01 and `last_month`
2026-05.

**February: Refund grain and a partial account.**

| Field | Value |
| --- | --- |
| `income` | 25,000.00 |
| `expenses` | 9,020.00: −(−8,500.00 − 640.00 + 120.00) |
| `net_cash_flow` | 15,980.00 |
| `savings_rate` | 0.6392 |
| `categories` | `rent` (`housing`) 8,500.00; `groceries` (`food`) 520.00: 640.00 − 120.00 |
| `unclassified`, `adjustments` | 0.00 in, 0.00 out, count 0 |
| `coverage` | `partial`: `joint-current` 2026-02 `partial` |
| `provisional` | null: February is closed and its rows are settled. |

The 120.00 Refund lowers both Expenses and `groceries`, and the categories add
up to Expenses: 520.00 + 8,500.00 = 9,020.00. In isolation: an expense of
100.00 and an expense-direction Refund of 20.00 in one Category give Expenses
of 80.00 and that Category's spending of 80.00. A Transfer or an Adjustment in
the same month changes neither.

**March: non-positive income and Unclassified money.**

| Field | Value |
| --- | --- |
| `income` | 0.00 |
| `expenses` | 1,000.00 |
| `net_cash_flow` | −1,000.00 |
| `savings_rate` | null: income is not positive. |
| `categories` | `utilities` (`housing`) 1,000.00 |
| `unclassified` | 0.00 in, −450.00 out, count 1 |
| `coverage` | `partial`: `joint-current` 2026-03 `partial` (the balance break) |
| `provisional` | null |

The Unclassified count is 1, so Enkel shows its quiet Unclassified note beside
money left of −1,000.00, and its Ukategoriseret figure shows `money_in` 0.00
and `money_out` −450.00, without the count. Were the 450.00 an
expense, money left would be 450.00 lower; were it a Transfer, it would stand.

**May: current month, no activity yet.** Income, Expenses and net cash flow
are 0.00, `savings_rate` is null, and `categories` is empty, under coverage
`partial` with both accounts' 2026-05 `partial`. `provisional` has both
reasons, with `unsettled` naming both accounts' 2026-05. The zeros are what the
evidence so far shows, not a confirmed quiet month.

**March, `joint-savings` only: a confirmed quiet month.** Every figure is
0.00, `savings_rate` is null, `categories` is empty, and coverage is
`complete` with no account-months listed. Here, and only because coverage is
complete, the absence of every Category is a known zero.

**June, reference date 2026-06-03: no data.** June is now `last_month`, so the
context is valid, but June is after the latest published month and neither
account has a row: both are `no_data`, and so is the report. Every figure is
null and `categories` is empty. `provisional` has both reasons, with
`unsettled` naming both accounts' 2026-06.

**A later account: `outside_history`.** Suppose the publication also had
`person-current`, whose first booked transaction is on 2026-04-03. February
with `joint-savings` and `person-current` selected lists `person-current`
2026-02 as `outside_history`. Coverage is `complete`, because `joint-savings`
is the only contributing account-month and it is `complete`.

**Invalid contexts.** An empty account selection raises `InvalidSelection`
with `no_accounts`. Selecting `joint-current` and `old-current`, which is not
in P1, raises it with `unknown_account` naming `old-current`. December 2025
raises it with `month_out_of_range`, because no account has a row before
2026-01. So does 2026-06 on reference date 2026-05-14, because it is in the
future.

**A newer build.** A page pinned to P1 keeps reading P1 after P2 becomes
current, and every report it reads then has `is_current` false. After P3 is
built, P1 is neither current nor previous, and unless it is labeled its result
is deleted: the page's next read raises `PublicationUnavailableError`.

**Spending detail.** Rows are `joint-current` sequence numbers in the Gold
example.

| Subject, scope, month | Rows | `spending` | Coverage, provisional |
| --- | --- | --- | --- |
| `groceries`, `month`, 2026-02 | seq 6 −120.00 (Refund), seq 5 640.00 | 520.00, as on the overview | `partial` (`joint-current` 02); not provisional |
| `groceries`, `year_to_date`, 2026-02 | seq 6, seq 5, seq 3 842.50 | 1,362.50 | `partial` (`joint-current` 01, 02; `joint-savings` 01); not provisional |
| group `housing`, `year_to_date`, 2026-04 | seq 10 `rent` 8,500.00, seq 9 `utilities` 1,000.00, seq 4 `rent` 8,500.00 | 18,000.00 | `partial`; not provisional |
| `groceries`, `year_to_date`, 2026-05 | as for 2026-02 | 1,362.50 | `partial`; both reasons, `unsettled` both accounts' 05 |
| `groceries`, `month`, 2026-06, reference date 2026-06-03 | none | null | `no_data`; both reasons |

`salary` (income), group `income` and `homeware` (not in P1) each raise
`unknown_category`.

**Selection transitions.** These run on the same P1 and reference date, in
February, with `A` meaning the selection `{joint-current}` and `B` meaning
`{joint-savings}`; the two reports carry different coverage.

- *Replies out of order.* The reader selects `A`, then `B`, before either
  answers. Only `B`'s response renders, so coverage describes `joint-savings`;
  the late `A` response is discarded.
- *`A -> B -> A`.* Returning to `A` asks again; the first `A`'s response is
  obsolete even if it arrives late.
- *Back and forward.* Back from `B` to `A` restores P1, the reference date, `A`
  and the mode, and reads `A` from P1 again, even after a refresh resolved P2.
- *A failure that stays visible.* A refresh with no current publication shows
  `NothingPublished`, not an empty report; a month outside P1's range shows
  `InvalidSelection` with `month_out_of_range`. Each stays visible while its
  generation is active, never leaving the previous figures as if they answered.
- *Empty selection during an outstanding request.* Selecting `A`, then clearing
  every account before it answers, discards the response, clears the figures
  and keeps the controls usable. A request made for the empty selection raises
  `InvalidSelection` with `no_accounts`.
