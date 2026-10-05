# Report Contract

## Status

Version `0.1`, this contract's first publication. The owner approved the
narrowed scope on 2026-10-04. It is accepted and effective for the scoped
release 0.2 upon merge of PR #190. Issue #101 is satisfied by accepted scoped
documentation, not by application code; what release 0.2 needs from it is the
shared report context, the monthly overview, the shared selection and failure
semantics, and the interaction transitions below.

It covers what the monthly overview needs: the report context, the monthly
overview report, and the failures a report read can raise. Category detail,
account activity, Kontrol checks, budget comparison, trends and history views
extend this document in their own tickets; [Deferred Sections and
Owners](#deferred-sections-and-owners) names each one, and nothing here
describes them until they land.
[Decisions about this document](https://github.com/ATherkel/budget/issues?q=is%3Aissue+is%3Aopen+%22report-contract.md%22).

## Purpose

Analytics produces household reports from Gold
([`analytics-layer.md`](analytics-layer.md)); presentation renders them
([`presentation-layer.md`](presentation-layer.md)). This document is the only
normative schema of the reports that pass between them. The production
analytics implementation and the synthetic report adapter used to develop
presentation both implement it, and share the examples below.

Analytics owns every financial figure, every coverage and provisional
judgement, and every validation rule here. Presentation formats and lays out
what it receives. It never sums, nets, or re-derives a figure, and it never
opens a Gold publication: it names one in the report context, and analytics
opens it.

## Value Types

| Type | Values / shape | Meaning |
| --- | --- | --- |
| `ReportingMonth` | `YYYY-MM` | As in [`gold-contract.md`](gold-contract.md#shared-value-types). |
| Money | `Decimal` | Exact amount in the report's currency, at that currency's minor units (DKK: two places). Never a float. |
| Ratio | `Decimal` | The unrounded quotient, computed in Python's default decimal context: 28 significant digits, rounded half-even. Rounding for display belongs to presentation. |
| `Coverage` | `complete`, `partial`, `no_data` | As in [`gold-contract.md`](gold-contract.md#shared-value-types). |
| `AccountMonthStatus` | `partial`, `no_data`, `outside_history` | Status of one selected account in one month that is not `complete`; see [Coverage](#coverage). |

When a report is serialized, for example in a fixture file or across a process
boundary, money is a decimal string with exactly the currency's minor-unit
places (`"-450.00"`), a ratio is the string form of its `Decimal`
(`"0.6392"`), a month is `"YYYY-MM"`, and a date is ISO 8601. Neither money nor
a ratio is ever a JSON number.

Signs: Income, Expenses and category spending are reported as positive
amounts, and a net Refund makes Expenses or a category's spending negative.
Net cash flow is negative when Expenses exceed Income. On the Unclassified and
Adjustment lines, money in is zero or positive and money out is zero or
negative.

## Interface

```python
class HouseholdReports(Protocol):
    def current_publication(self) -> ReportPublication: ...

    def selection_options(
        self, publication_id: int, reference_date: date
    ) -> SelectionOptions: ...

    def monthly_overview(self, context: ReportContext) -> MonthlyOverview: ...
```

`current_publication()` raises `NothingPublished` when Gold has no current
publication. `selection_options()` and `monthly_overview()` raise
`PublicationUnavailable` when the named publication's result is not retained,
and `monthly_overview()` raises `InvalidSelection` for a context that breaks a
rule under [`ReportContext`](#reportcontext). A failure is never returned as an
empty or zero report.

### `ReportContext`

The one selection every report on a page shares.

| Field | Type | Meaning |
| --- | --- | --- |
| `publication_id` | int | The publication every report on the page reads. |
| `account_ids` | set of string | The selected accounts. Any non-empty combination, regardless of ownership. |
| `month` | `ReportingMonth` | The selected month. A report covering several months will take its range as its own parameter, anchored to this month. |
| `reference_date` | `date` | The date the provisional rule is judged on. Analytics never reads a clock. |

A page resolves its context once: it asks for the current publication and
takes today's date in Europe/Copenhagen as the reference date. Every follow-up
request from that page, such as a fragment or a drill-down, carries the same
`publication_id` and `reference_date`, so one page never mixes two
publications or two days. A reload resolves a fresh context. On a fresh visit
the selection is every account in `SelectionOptions.accounts` and the month of
the reference date.

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
| `accounts` | list of `SelectableAccount` | Every `GoldAccount` in the publication, ordered by `account_id`: `account_id`, `display_name`, `account_type`, `ownership_scope`, `currency`. Every Gold account is inside the Reporting boundary, so this is "all imported accounts". |
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

A page pinned to a publication keeps reading it after a newer build becomes
current, for as long as its result is retained, so the page's parts never mix
two publications. `is_current` turns false on the first report read after the
newer build, so the page can say that newer figures exist and offer a reload.
Once the result is deleted, the next read raises `PublicationUnavailable`, and
the page offers the current publication explicitly instead of substituting it.

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
| `categories` | list of `CategorySpending` | One row per expense-direction Category with at least one allocation in the month, ordered by `category_id`. Empty when `coverage.status` is `no_data`. |
| `unclassified` | `MoneyInOut`/null | Unclassified money: `unknown` transactions. |
| `adjustments` | `MoneyInOut`/null | `adjustment` transactions, which carry no allocation. |
| `coverage` | `ReportCoverage` | Coverage of every figure above. |
| `provisional` | `Provisional`/null | Why the month is provisional; null when it is not. |

`income`, `expenses`, `net_cash_flow`, `unclassified` and `adjustments` are
null exactly when `coverage.status` is `no_data`: with no evidence, a figure is
unknown, never zero. A `partial` report carries the amounts known from the
evidence that exists, and presentation shows them only with the coverage the
report carries.

Income and Expenses are summed over transactions, and category spending over
category allocations (ADR-008); the two are never added together. Category
spending therefore always adds up to Expenses. Transfers are excluded from
every figure, whichever accounts are selected (Gold contract invariant 8). An
absent Category means no categorized expense in the month; it is a known zero
only when `coverage.status` is `complete`.

`CategorySpending`: `category_id`, `name`, `group_id`, `group_name`, and
`spending`, the Category's net spending as Money: −(Σ allocations of `expense`
transactions + Σ allocations of `refund` transactions), negative when Refunds
exceed purchases. The overview carries no Category group totals and no
transaction rows; reports that need them add them.

`MoneyInOut`: `money_in` (Σ positive amounts), `money_out` (Σ negative
amounts), and `count`. The two amounts are never netted, so offsetting entries
cannot read as nothing.

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

The contributing account-months are the selected ones that are not
`outside_history`. `status` is `complete` when every contributing
account-month is `complete`, `no_data` when none has evidence (including when
none contributes), and `partial` otherwise. One status covers every figure in
the report because every figure draws on the same contributing account-months:
the selected accounts in the selected month.

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

An account without a managed period never holds the label: one never imported
is exempt by the rule, and one imported without a booked transaction is the
rule's known first-release limitation. An `outside_history` month cannot hold
it either.

## Navigation and Selection Transitions

This section fixes the interaction a page owes its reader. It is route-neutral:
the contract constrains what the reader is shown, never the transport or the
shape of a URL. The report DTOs above carry no HTML-, URL-, or
framework-specific schema.

**One pinned context.** A page resolves its context once, as defined under
[`ReportContext`](#reportcontext), and pins `publication_id` and the Copenhagen
`reference_date` for the whole visit. Ordinary navigation inside the page - an
account or month change, a fragment, a drill-down, a mode change, an ordinary
link or a form - keeps that pin and never re-resolves it from the clock or from
whichever publication is current. Only an explicit refresh, or an explicit
return to the current publication, resolves a fresh context.

**Central validation.** Every candidate selection, restored or freshly entered,
is validated against the publication its context pins, by the rules under
[`ReportContext`](#reportcontext), before it is used. Validation never resolves
the current publication and never repairs a selection behind the reader's back.

**Response eligibility.** A successful report response may render only when
both hold:

1. it answers the activity that is current now: the navigation change or
   request generation that asked for it is still the active one; and
2. its echoed `context` equals the active validated selection on all four
   fields, with `account_ids` compared canonically as a set.

A successful response that fails either test is discarded. A selection change
therefore invalidates every outstanding response for the previous selection
before any replacement is rendered, so figures that answered one selection can
never appear under the controls of another. Returning to an earlier selection is
a new request: `A -> B -> A` does not revive the response that answered the
first `A`.

**Failures.** A failure carries no report and no echoed context, so it is
matched to the active request generation and the candidate selection it was
raised for instead. `NothingPublished`, `InvalidSelection` and
`PublicationUnavailable` must not be made to invent an echoed valid
`ReportContext`. A failure raised for the current generation displays: an
`InvalidSelection` names the rules it broke, `NothingPublished` says no
publication exists, and `PublicationUnavailable` offers the current publication
explicitly. A failure whose generation is superseded is discarded, so a late
error cannot replace the result of a newer successful selection either.

**Empty selection.** A context with no accounts selected is an intentional
prompt, not a report. Presentation invalidates outstanding responses, clears or
hides the previous financial output, keeps the account controls usable, and
does not let a late response repaint figures. Analytics keeps its rule: a
request actually made for an empty selection raises `InvalidSelection` with
`no_accounts`, because an empty selection is never a successful zero report.

**Back and forward.** A browser history entry carries the full state it belongs
to: the pinned `publication_id`, the `reference_date`, the account and month
selection, and the mode. Going back or forward restores that state even when an
explicit refresh has resolved another context since, validates it against the
publication it pins rather than against what is current now, and reads again
under a fresh request generation. A restored context whose publication result
is no longer retained stays explicit as `PublicationUnavailable`; a restored
selection that breaks a rule stays explicit as `InvalidSelection` naming the
rules it broke; a restored empty selection restores the prompt. No restored
state falls back to the current publication, to the default selection, or to
whatever the reader was looking at before. Ordinary links and forms the page
follows preserve the pin the same way.

**Explanation of coverage and provisional figures.** The explanation stays
reachable within the same context: the page offers the report's own incomplete
account-months and provisional reasons without leaving the pinned context or
resolving a new one (issue #104). It does not require the Kontrol screen, which
arrives later (issue #106). Analytics owns the judgements the explanation
shows, which issue #179 implements; presentation owns the destination and the
way it is reached.

**Ownership in 0.2.** Pinning the publication, the notice that a newer build
exists, `PublicationUnavailable` recovery, and the coverage and provisional
explanation are 0.2 responsibilities (issues #103, #104, #180 and #111). The
history picker and history-specific verification arrive later (issue #109).

**Report figures and browser storage.** Navigation state and browser storage
carry no financial payload at all: they hold the pinned identity and the
selection, and nothing else, and no new financial model appears
([`presentation-layer.md`](presentation-layer.md#non-responsibilities)). The
rendered HTML necessarily displays the figures the reader is looking at; this
rule governs what is stored and reused, not what is displayed.

## Deferred Sections and Owners

Each entry names the ticket that extends this document with its own report
section and approved examples before application implementation. Nothing is
deleted: a section moves to its owner.

| Section | Owner | What the owner adds here |
| --- | --- | --- |
| Category and group detail | #105 | Allocation identity and amount against transaction identity and amount, month and year-to-date scope, and Refund and coverage semantics. |
| Account and Kontrol diagnostics | #106 | Dated bank balances against monthly snapshots, public Transfer evidence including one-sided and unknown restrictions, Evidence through, and reconciliation and count semantics. |
| Budget input | #102 | Publication and recipe identity, immutable history, and the exact scope, completeness and availability policy. |
| Budget comparison | #107 | The comparison report that follows #102: targets, variance and ratios, with their availability. |
| Trend report | #108 | Ranges, grouped selection, gaps, trust per point, and the budgets some points depend on. |
| Historical navigation | #109 | Known-at reference dates and plan history, the banner and picker, and legacy-specific behaviour. |

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
| `categories` | `groceries` (`food`) 520.00: 640.00 − 120.00; `rent` (`housing`) 8,500.00 |
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
is deleted: the page's next read raises `PublicationUnavailable`.

**Selection transitions.** These run on the same P1 and reference date, in
February, with `A` meaning the selection `{joint-current}` and `B` meaning
`{joint-savings}`; the two reports carry different coverage.

- *Replies out of order.* The reader selects `A` and then `B` before either
  answer arrives. Only the `B` response renders, so the coverage line describes
  `joint-savings`; the late `A` response is discarded instead of painting its
  figures under the `B` controls.
- *`A -> B -> A`.* Returning to `A` asks again. The response that answered the
  first `A` is obsolete even when it arrives late, and the page renders only the
  answer to the current `A`.
- *Back and forward.* Back from `B` to `A` restores that entry's full state:
  the pinned P1, the reference date, the `A` selection and the mode. The page
  revalidates the restored selection against P1 rather than against whatever is
  current then, and reads again under a fresh request generation. This holds
  when an explicit refresh has since resolved P2: history entries that pin P1
  still restore P1 while its result is retained, and stay an explicit
  `PublicationUnavailable` once it is deleted. A restored empty selection
  restores the prompt instead of reading.
- *A failure that stays visible.* An explicit refresh resolves a fresh context;
  with no current publication the page shows `NothingPublished` instead of an
  empty report. Selecting a month outside P1's range shows `InvalidSelection`
  with `month_out_of_range`. Neither failure carries an echoed context, and
  each stays visible while it is the active generation rather than leaving the
  previous figures on screen as if they answered the new selection.
- *Empty selection during an outstanding request.* The reader selects `A`, then
  clears every account before the answer arrives. The outstanding response is
  discarded, the figures are cleared, and the account controls stay usable. A
  request actually made for the empty selection raises `InvalidSelection` with
  `no_accounts`.
- *Publication removal and supersession.* A page pinned to P1 keeps reading P1
  while P2 is current, with `is_current` false and the superseded-page notice.
  Changing account or month still reads P1. Once P3 is built and P1's result is
  deleted, the next read raises `PublicationUnavailable`, and the page offers
  the current publication explicitly rather than substituting it.
