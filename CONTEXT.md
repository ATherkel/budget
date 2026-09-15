# Household Finance

A platform that turns imported bank exports into trustworthy household financial
reporting: reproducible Bronze → Silver → Gold transformation feeding read-only
analytics and a dashboard.

## Language

### Accounts and boundary

**Reporting boundary**:
The set of accounts whose activity household reports include: the imported
accounts, each with `ownership_scope` of `household` or `person`. Every other
account is `external`, including a household member's account that the
household does not import; money to or from it is income or expense, never a
Transfer.
_Avoid_: Household accounts (ambiguous with `ownership_scope=household`)

**Transfer-eligible account**:
An account inside the household reporting boundary — `ownership_scope` of
`household` or `person` — whose movements can be matched as an internal
Transfer. An `external` account can never be presumed the other leg of a
Transfer.
_Avoid_: Household account (too narrow; excludes person-owned accounts that are
still transfer-eligible)

**Managed period**:
The span of reporting months in which an account is part of the household's
history: from the month of its first Booked transaction until the month it
closes, or the latest reported month if it is still open. A month outside it
is not a gap; a month inside it with no transactions is `no_data`.
_Avoid_: Active period, account lifetime (the bank account may predate the
household's data)

### Transactions and classification

**Booked transaction**:
A transaction whose source marked it completed/settled. A pending or
unsettled source row is retained in Bronze and Silver as provenance but never
becomes a Gold transaction. A booked transaction is classified as a whole: it
carries at most one category and is never split across categories.
_Avoid_: Transaction, in Bronze/Silver context (too broad — those layers may
hold unsettled rows that aren't Transactions yet); split, allocation (not a
concept this release has)

**Classification**:
A booked transaction's household interpretation: its type and, for income,
expense, or Refund, its Category. It comes from a Manual decision, a matched
Transfer, or a Classification rule; without one, the transaction is
unclassified.
_Avoid_: Categorisation (narrower), tagging

**Classification rule**:
A household-authored pattern over one transaction's own facts that assigns a
Category, claims the transaction as a Transfer leg, or marks an Adjustment. A
rule never looks at other transactions.
_Avoid_: Mapping, filter

**Category**:
A household-defined heading for income or spending, with a direction of
`income` or `expense`. It is the only thing assigned to a transaction.
_Avoid_: Bank category (a different thing)

**Bank category**:
The category label a bank puts on its own export rows. It is provenance: a
Classification rule may test it, but it never becomes a Category by itself.
_Avoid_: Category, when meaning the bank's label

**Transfer**:
Money moved between two accounts inside the Reporting boundary. It shows as
two booked transactions, its legs, one on each account. A Transfer is either a
matched pair of legs or, by Manual decision, one-sided when the other leg lies
outside the counterpart's Managed period.
_Avoid_: Internal transfer (redundant), movement

**Refund**:
Money returned against a prior purchase. Nets against the originating category's
expense total rather than counting as income or vanishing from spending.
_Avoid_: Reversal (see Adjustment), chargeback (not yet a distinct concept)

**Adjustment**:
A correction, fee reversal, or exceptional entry with no originating purchase to
net against; excluded from income and expense totals. A Refund is not an
Adjustment even though both break the expense-is-negative sign convention.

**Category group**:
The fixed top level of the two-level category hierarchy. It gathers related
categories of one direction for reporting and is never assigned to a
transaction directly.
_Avoid_: Parent category, super-category

**Unclassified total**:
An explicit reporting measure summing `unknown`-classified transactions for a
period, shown alongside Income/Expenses/Savings so an unclassified amount is a
verified claim, not an artifact of silent exclusion.

### Balances and trust

**Balance chain**:
The reconciliation evidence for an account: each transaction carries the
bank-stated balance immediately after it, which must equal the last known
balance plus every amount booked since. The account's first transaction is
trusted as its opening balance, and a break re-anchors the chain on the
break's own stated balance. A break, or a missing balance, is a discrepancy —
reflected in Coverage, never silently corrected.

**Coverage**:
A per-account, per-reporting-period status (`complete` / `partial` / `no_data`)
stating whether that account's data is trustworthy enough to report on for that
period. `complete` requires an unbroken balance chain across every row in the
period _and_ that the period is not the first month of the account's Managed
period; a first, partial-month import is always `partial`. A chain break makes
every month from the last trusted balance through the break `partial`, because
the missing movement could lie anywhere in that span. Tracked at the account
grain, not the whole household, so a gap points at the account that needs
attention.

**Monthly balance snapshot**:
One account's balance position for one reporting month of its Managed period:
the balance before the month's first transaction, the balance after its last,
and the month's Coverage. Balances add up across accounts for the same month,
never across months.
_Avoid_: Statement (a bank document), balance on its own (ambiguous with the
bank-stated balance after one transaction)

**Provisional period**:
A reporting period that includes the current, still-accumulating calendar
month. Must be visibly labeled wherever it's displayed, not just documented.

### Review

**Review item**:
An ambiguity the platform cannot settle by rule and a person must decide, such
as overlapping exports that disagree, Classification rules that conflict, or
Transfer legs that compete for the same match.
_Avoid_: Error, warning, conflict

**Manual decision**:
A recorded human ruling: it classifies a transaction, settles a Review item,
or voids an import run. It targets transactions by their identity and never
edits source data.
_Avoid_: Override, fix, edit
