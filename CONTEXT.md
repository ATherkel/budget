# Household Finance

A platform that turns imported bank exports into trustworthy household financial
reporting: reproducible Bronze → Silver → Gold transformation feeding read-only
analytics and a dashboard.

## Language

### Accounts and boundary

**Reporting boundary**:
The set of accounts whose activity household reports include: every account
with `ownership_scope` of `household` or `person`. An `external` account sits
outside it and is never an imported, reported account.
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
is outside the reported history; a quiet month inside it is judged by Coverage.
_Avoid_: Active period, account lifetime (the bank account may predate the
household's data)

### Transactions and classification

**Booked transaction**:
A transaction whose source row Silver maps to `booking_status=booked`.
Pending and cancelled rows remain provenance. A booked transaction carries
at most one category and is never split across categories.
_Avoid_: Transaction in Bronze/Silver (too broad); split, allocation

**Refund**:
Money returned against an earlier categorized movement. It nets against that
category in the originating measure, including a reversed fee or returned income.
_Avoid_: Reversal (ambiguous with Adjustment), chargeback (not distinct yet)

**Adjustment**:
An uncategorized correction, excluded from income and expense totals and
reported separately. A Refund carries a category and is not an Adjustment.

**Category group**:
The fixed top level of the two-level category hierarchy. It gathers related
categories for reporting and is never assigned to a transaction directly.
_Avoid_: Parent category, super-category

**Unclassified money**:
Money on `unknown` transactions, reported as money in, money out, and a count,
so opposite amounts can't cancel to zero and read as "nothing unclassified".
_Avoid_: Unclassified total (a single sum hides offsetting amounts)

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
saying whether the balance evidence shows that the whole period is covered.
The rules are in [`gold-layer.md`](docs/architecture/gold-layer.md#coverage).
A quiet month can be complete; absent evidence cannot be read as zero.

**Evidence through**:
The last date an account's admitted exports are known to cover: the day
before its latest admitted export date.
_Avoid_: last import date

**Monthly balance snapshot**:
One account's balance position for one reporting month of its Managed period:
the balance before the month's first transaction, the balance after its last,
and the month's Coverage. Balances add up across accounts for the same month,
never across months.
_Avoid_: Statement (a bank document), balance on its own (ambiguous with the
bank-stated balance after one transaction)

**Provisional period**:
A reporting period that includes the current calendar month or still awaits
exports covering the late-booking window. How it must be labeled is in
[`docs/architecture/presentation-layer.md`](docs/architecture/presentation-layer.md#data-trust-display).

### Imports and identity

**Export**:
A file the bank produces for one account, reaching up to its export date.
Overlapping exports of the same account are normal.
_Avoid_: statement, dump

**Transaction date**:
The date the source assigns to a transaction; for Danske, the purchase date.
It determines the reporting period.
_Avoid_: booking date, value date

**Late booking**:
A transaction the bank books days after its transaction date, so it first
appears in a later export on a date an earlier export already covered.
_Avoid_: back-dated transaction, missing transaction

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
