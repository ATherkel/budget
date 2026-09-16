# Household Finance

A platform that turns imported bank exports into trustworthy household financial
reporting: reproducible Bronze → Silver → Gold transformation feeding read-only
analytics and a dashboard.

## Language

### Reporting

**Refund**:
An Adjustment that carries a `category_id`. It nets against that category
instead of counting as income or vanishing from spending. A reversed fee is a
Refund against the fee's category.
_Avoid_: Reversal, chargeback (not yet a distinct concept)

**Adjustment**:
A transaction that breaks the income/expense sign convention. With a
`category_id` it is a Refund; without one it is a correction. How each is
treated is in [`docs/domains/transaction.md`](docs/domains/transaction.md#types).

**Transfer-eligible account**:
An account inside the household reporting boundary — `ownership_scope` of
`household` or `person` — whose movements can be matched as an internal
Transfer. An `external` account can never be presumed the other leg of a
Transfer.
_Avoid_: Household account (too narrow; excludes person-owned accounts that are
still transfer-eligible)

**Coverage**:
A per-account, per-reporting-period status (`complete` / `partial` / `no_data`)
saying whether that account's balance evidence shows the period's data is
whole. It is judged over the whole period, not only the rows inside it; the
rules are in
[`docs/architecture/analytics-layer.md`](docs/architecture/analytics-layer.md#coverage).
Tracked per account, not for the whole household, so a gap points at the
account that needs attention.

**Balance chain**:
The reconciliation evidence for an account: each transaction carries the
bank-stated balance immediately after it, and each link between consecutive
transactions checks that the later balance equals the earlier one plus the
later amount. A broken link, or a missing balance, is a discrepancy, never
silently corrected.

**Evidence through**:
The last date an account's imported exports are known to cover, computed from
its admitted exports by the formula in
[`docs/architecture/silver-layer.md`](docs/architecture/silver-layer.md#evidence-through).
_Avoid_: last import date (the export, not the import, bounds the evidence)

**Covers through**:
The last date one export's evidence reaches: the end of the range the operator
asked the bank for, declared at import. Distinct from the *export date*, so a
year of history exported today is not read as covering today.
_Avoid_: export range, to-date

**Booked transaction**:
A transaction whose source row Silver maps to `booking_status=booked`. A
`pending` or `cancelled` source row is retained in Bronze and Silver as
provenance but never becomes a Gold transaction.
_Avoid_: Transaction, in Bronze/Silver context (too broad — those layers may
hold pending or cancelled rows that aren't Transactions)

**Unclassified money**:
Money on `unknown` transactions, reported as money in, money out, and a count,
so opposite amounts can't cancel to zero and read as "nothing unclassified".
_Avoid_: Unclassified total (a single sum hides offsetting amounts)

**Provisional period**:
A reporting period that includes the current calendar month or still awaits
exports covering the late-booking window. How it must be labeled is in
[`docs/architecture/presentation-layer.md`](docs/architecture/presentation-layer.md#data-trust-display).

### Imports and identity

**Export**:
A file the bank produces for one account, covering a date range the operator
chose. Overlapping exports of the same account are normal.
_Avoid_: statement, dump

**Export date**:
The date the bank produced an export, from the filename suffix or declared at
import. It says when the file was made, not how far it reaches; the
late-booking window is counted from it.
_Avoid_: import date, range end

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
