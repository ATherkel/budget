# Household Finance

A platform that turns imported bank exports into trustworthy household financial
reporting: reproducible Bronze → Silver → Gold transformation feeding read-only
analytics and a dashboard.

## Language

### Reporting

**Refund**:
Money returned against a prior purchase. Nets against the originating category's
expense total rather than counting as income or vanishing from spending.
_Avoid_: Reversal (see Adjustment), chargeback (not yet a distinct concept)

**Adjustment**:
A correction, fee reversal, or exceptional entry with no originating purchase to
net against; excluded from income and expense totals. A Refund is not an
Adjustment even though both break the expense-is-negative sign convention.

**Transfer-eligible account**:
An account inside the household reporting boundary — `ownership_scope` of
`household` or `person` — whose movements can be matched as an internal
Transfer. An `external` account can never be presumed the other leg of a
Transfer.
_Avoid_: Household account (too narrow; excludes person-owned accounts that are
still transfer-eligible)

**Coverage**:
A per-account, per-reporting-period status (`complete` / `partial` / `no_data`)
stating whether that account's data is trustworthy enough to report on for that
period. `complete` requires an unbroken balance chain across every row in the
period _and_ that the account was already under management before the period
began; a first, partial-month import is always `partial`. Tracked at the
account grain, not the whole household, so a gap points at the account that
needs attention.

**Balance chain**:
The reconciliation evidence for an account: each transaction carries the
bank-stated balance immediately after it, which must equal the previous
transaction's balance plus its amount. The account's first transaction is
trusted as its opening balance. A break, or a missing balance, is a
discrepancy that is never silently corrected.

**Booked transaction**:
A transaction whose source marked it completed/settled. A pending or
unsettled source row is retained in Bronze and Silver as provenance but never
becomes a Gold transaction.
_Avoid_: Transaction, in Bronze/Silver context (too broad — those layers may
hold unsettled rows that aren't Transactions yet)

**Unclassified total**:
An explicit reporting measure summing `unknown`-classified transactions for a
period, shown alongside Income/Expenses/Savings so an unclassified amount is a
verified claim, not an artifact of silent exclusion.

**Provisional period**:
A reporting period that includes the current, still-accumulating calendar
month. Must be visibly labeled wherever it's displayed, not just documented.

### Imports and identity

**Export**:
A file the bank produces for one account covering a date range. Overlapping
exports of the same account are normal.
_Avoid_: statement, dump

**Raw payload**:
The exact bytes received from a source, such as an export file or an API
response. It is never altered.
_Avoid_: raw data, original file

**Import run**:
One presentation of a raw payload to the platform, together with the account
the operator declared it belongs to.
_Avoid_: import, load, upload

**Source record**:
One record exactly as the source presented it, such as an export row, still
uninterpreted.
_Avoid_: raw row, line

**Unbooked record**:
A source record the source marks as not booked, such as pending or deleted
before booking. It is retained as provenance but never becomes a booked
transaction.
_Avoid_: pending transaction, deleted transaction, cancelled transaction

**Duplicate**:
The same booked transaction appearing in more than one source record,
typically in overlapping exports. Duplicates collapse to one booked
transaction.
_Avoid_: repeat, copy

**Repeated transaction**:
One of several distinct booked transactions that look identical: same account,
date, amount, and text. Each one is kept.
_Avoid_: duplicate

### Review

**Quarantine**:
The state of an import run whose raw payload is retained but which contributes
nothing downstream, because it failed validation or awaits review.
_Avoid_: rejected, held, failed import

**Review item**:
An ambiguity the platform cannot settle by rule and a person must decide, such
as overlapping exports that disagree or a later export showing fewer repeated
transactions.
_Avoid_: error, warning, conflict

**Manual decision**:
A recorded human ruling that settles a review item or voids an import run. It
never edits source data.
_Avoid_: override, fix, edit

**Voided import run**:
An import run a person has declared mistaken, for example because it was
declared against the wrong account. Its raw payload is retained but it
contributes nothing downstream.
_Avoid_: deleted import, undone import
