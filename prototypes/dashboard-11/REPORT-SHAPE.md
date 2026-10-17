# Proposed analytics interface for the monthly dashboard

**29 September 2026:** retained as prototype design evidence. The newer
[implementation specification #100](https://github.com/ATherkel/budget/issues/100)
and contract tasks [#101](https://github.com/ATherkel/budget/issues/101) /
[#102](https://github.com/ATherkel/budget/issues/102) supersede this document's
scope and open preference questions. In particular, read-only monthly budget
comparison is now first-release scope and is available in Enkel. This historical
DTO proposal is still not an accepted production contract.

🤖 Added by Codex (GPT-6 Astra)

**Status: proposal for the maintainer. Nothing here is accepted, and no ADR is
changed by it.** It uses the vocabulary of [CONTEXT.md](../../CONTEXT.md) and
the accepted rules in [gold-contract.md](../../docs/architecture/gold-contract.md)
(0.2), [analytics-layer.md](../../docs/architecture/analytics-layer.md),
[publications.md](../../docs/architecture/publications.md),
[classification.md](../../docs/architecture/classification.md) and
[operations.md](../../docs/architecture/operations.md). It was written from what
the screen in this folder needs, then reconciled with those documents; where
they disagree, they win and this file is wrong.

The screen in `prototypes/dashboard-11/` receives finished reports and renders
them. It reads no bank data, computes no financial figure, and makes no
classification decision. The one-time preparation that produced
`example.json` is a throwaway fixture builder (`build_example.py`), not an
import engine and not proposed for production.

Technical field names stay in English. Everything a user reads stays Danish.

## What one page reads

One page reads exactly one **publication** (ADR-014). Every report the page
renders carries that publication's identity, so a page can never mix two
publications, and a past view is never the current data relabelled.

```text
PublicationIdentity
  publicationId: string
  kind: pipeline | as_was | as_known_at
  label: string                 // household-facing name of the view
  knownAt: date                 // the knowledge the publication represents
  isCurrent: boolean

ReportRequest
  publicationId: string
  accountIds: id[]              // any combination, independent of ownership
  month: YYYY-MM
  trendPeriod: {startMonth, endMonth}

MonthlyReport
  publication: PublicationIdentity
  currency: ISO 4217 string      // DKK in this prototype
  accountIds: id[]
  period: {id, label, start, end, provisional, provisionalReasons[], statusLabel, detail}
  coverage: {status, label, shortLabel, detail,
             incompleteAccounts: [{id, name, status, reason}]}
  measures: {income, expenses, netCashFlow, savings, savingsRate, coverage}
  incomeTransactions: TransactionDisplay[]
  categories: [{id, name, purchases, refunds, netSpending,
                coverage, transactions: CategoryDrilldownRow[]}]
  unclassified: {moneyIn, moneyOut, count, detail, transactions}
  adjustments: {moneyIn, moneyOut, count, detail, transactions}
  transfers: {moneyIn, moneyOut, count, pairedCount, oneSidedCount,
              label, detail, transactions}
  accounts: [{id, name, ownerLabel, accountType, ownershipScope,
              coverage, evidenceThrough,
              balance: {amount|null, asOf|null}, quietConfirmed,
              activityNote, transactions: TransactionDisplay[]}]

TrendReport
  publicationId, currency, accountIds, startMonth, endMonth, asOf
  months: [{month, income|null, expenses|null, netCashFlow|null,
            provisional, provisionalReasons[], coverage}]

AvailableAccounts: [{id, name, ownerLabel, accountType, ownershipScope, managedFrom}]

TransactionDisplay
  id, accountId, accountName, date, description, amount, kind, kindLabel, category

CategoryDrilldownRow
  allocationId, transactionId, accountId, accountName, date, description,
  transactionAmount, allocationAmount, kind, kindLabel

// transfer legs only, on TransactionDisplay:
  transferGroupId|null, transferBasis: paired|one_sided
```

Amounts are exact decimal strings in one currency. Money out is negative.
Expense and category totals are positive for spending and may be negative when
refunds exceed purchases. The share left over is null when income is not
positive. The browser calculates no financial figure.

`savingsRate` **has a unit that must be stated**, because the two layers do not
agree today: `analytics-layer.md` defines Savings rate as the ratio
`savings / income`, while the prototype carries percentage points (58.03). A
production field should be named for its unit — a ratio
(`savingsRateRatio`), or a percentage-point field whose name says so — and the
screen must not guess. `savings` stays what the analytics layer defines:
income − expenses, equal to net cash flow in this release.

A category drill-down lists **allocations, not transactions**. With one
allocation per classified transaction today, `allocationAmount` equals
`transactionAmount`, but a split transaction produces several rows whose
allocation amounts sum to the transaction amount and whose signs match their
transaction. A screen that renders `TransactionDisplay.amount` per row would
double-count a split, so the drill-down row carries the allocation's own
`allocationId` and `allocationAmount`.

## Rules this proposal follows

**Refund direction.** A refund reverses the direction of the category it is
allocated to (Gold contract invariant 3). For an expense category it is a
positive amount that nets into that category, so a category total can be
negative — a net refund. It is never clamped to zero and never moved to the
purchase's month. Expenses fall by the same amount, because Expenses is
−(Σ expenses + Σ refunds with direction expense).

**Allocations, not transactions, sum the categories.** Category and
category-group spending is summed over `GoldCategoryAllocation.amount`, and
household income and expenses over `GoldTransaction.amount`. The two agree
today because one classified transaction has exactly one allocation equal to
its amount. A report must never sum a transaction and its allocations together:
that is the same money twice. Once a transaction can carry several
allocations, the category view still adds up to Expenses, and a consumer that
already reads allocations needs no change.

**An adjustment carries no category.** `adjustment` transactions have no
allocation at all, so a report group shows them separately as money in, money
out and a count, and they never reach Income or Expenses. A refund is not an
adjustment: it keeps its category.

**Two kinds of transfer evidence, and they are told apart on screen.** Both
legs of a paired transfer share a `transfer_group_id`, derived from their
transaction identifiers, and their amounts cancel. A one-sided transfer comes
only from a manual `one-sided-transfer` decision and has no group; Gold
invariant 17 requires its counterpart account's managed period to exclude the
transaction date. A transfer — paired or one-sided — is excluded from income,
expenses, savings-rate and category spending, and stays visible in account
activity. That exclusion does not depend on which accounts a page selects: a
transfer leg keeps its meaning even when the other account is not selected,
and the analytics layer states the rule without reference to the selection.

The accepted public Gold contract has no projection of a one-sided transfer's
counterpart: the counterpart is transfer evidence, and a claim that found no
counterpart exposes its review item only through the privileged lineage
interface. The prototype names the counterpart account because its fixture
states it (see the prototype-only list below). The simplest honest production
copy is therefore generic — *Enkeltsidet overførsel, afgjort manuelt, uden det
andet ben i de valgte kontoudtog* — and needs no new or privileged contract
field.

**An unmatched claim is only unclassified money.** A transfer claim that finds
no counterpart is `unknown` (ADR-011/ADR-012). It reaches the report through
the unclassified group, and its review item — `unmatched-transfer`, with a
reason such as `no-candidate` or `counterpart-may-not-be-imported` — stays in
Gold's privileged lineage interface, which analytics and presentation may not
read. The report carries no review reason, no rule identifier and no decision
identifier. Missing categories are settled outside the screen with
`budget review` and `budget decide`; naming that route is documentation, and
the screen executes nothing.

**Coverage on every measure.** Every household-level measure carries combined
coverage: `complete` only when every contributing account-month is complete,
`no_data` when none has evidence, `partial` otherwise. A partial measure names
its incomplete accounts, and a shared compact line is enough when it clearly
covers the figures it sits with. Coverage is not summarised away by a
household-level flag.

**Balances and evidence.** A balance is the account's latest bank-stated
closing balance with the date it was stated; an unknown balance is null, never
zero, and it may not suggest that a partial month is complete. Each account
carries `evidence_through` — the last date its admitted exports cover — so the
screen can say how far the data reaches.

**Provisional is a separate question.** Three different conditions are shown
separately: a provisional period, missing or partial account data, and money
without a category. A period that contains the current month always carries
the provisional label. A closed period keeps it until every account has an
admitted export that was produced at least seven days after the period's end
and covers the period's last day; an account never imported is exempt. A past
view takes the provisional label as of its `knownAt`, not as of today, and the
synthetic "today" is stated on the screen.

**Counts and reconciliations are report fields.** The screen must be able to
show that income − expenses = the amount left, that the categories add up to
Expenses, and how many entries sit in each group, without adding anything up in
the browser. Either the analytics layer returns those figures, or the screen
shows no reconciliation at all.

## Where the prototype goes beyond the proposal

These fields exist only to make the throwaway prototype auditable. They are not
proposed as part of the production contract:

- `barPercent` (a bar width, precomputed so the browser divides nothing);
- `openingBalance` and the per-month balance chain the fixture checker asserts;
- `reconciliation` (the counts and the precomputed `categoryTotal`);
- `unclassified.operatorRoute` (the `budget review` / `budget decide` copy);
- `budgetExample` (the budgeting experiment, kept in Advanced and explicitly
  outside the first delivery);
- `measureNote`, `activityNote`, `transferLabel`, `statusLabel` and `detail`
  (display copy that the fixture already carries so the screen needs no
  translation table);
- `counterpartAccountId` and `counterpartAccountName` on a one-sided transfer
  leg: the fixture states the counterpart, the accepted public contract does
  not project it, and a production screen should use the generic copy above
  instead of asking for a privileged projection;
- `availableAccounts.managedFrom` (used only to prove the one-sided transfer
  invariant in the fixture);
- `accounts.openingBalance` and `accounts.quietConfirmed` (the second is likely
  worth keeping in production: "no movements, and the statements confirm it").

## Gaps this round found

1. **A month outside the managed period cannot be told from a month with no
   admitted evidence.** The public DTO has `complete` / `partial` / `no_data`,
   and `no_data` now covers both "the household has no evidence for this month"
   and "the account's history does not include this month at all". The
   prototype labels both `no_data` and names the reason in prose
   (`Kontoudtoget begynder først i maj 2026`). A production report either adds
   a reason code or keeps reporting the reason as text.
2. **A one-sided transfer needs its counterpart in the public DTO** to be
   explained. Today the screen can name it only because the fixture states it.
   Either `transfer_evidence` gains a public, non-privileged projection, or the
   display stays "a transfer with no counterpart in these statements".
3. **`savings` still means income − expenses.** The budget experiment shows a
   second, different figure ("contribution to ordinary savings after
   earmarking"). It must not quietly replace the analytics measure; the naming
   decision belongs to the budget scope, not to this prototype.
4. **Whether the mode choice is remembered** is still undecided. The prototype
   keeps it in memory only and stores nothing in the browser.

## Open questions for the maintainer

- Do both participants understand the three figures, the short category list,
  and the difference between "no evidence" and "confirmed quiet"?
- Is "Tilbage efter udgifter" (income − expenses) the best headline figure, and
  is the separate "contribution to ordinary savings" worth a second headline?
- Is income − expenses the right measure at all? Money moved to an account
  *outside the reporting boundary* is the open question (Gold contract and
  issue #12); a transfer *inside* it is settled by the analytics layer and is
  excluded from income and expenses however the account selection is made.
- Which fields of this proposal should become the accepted analytics
  interface, and which belong to a later scope decision?
