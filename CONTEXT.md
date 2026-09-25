# Household Finance

A platform that turns imported bank exports into trustworthy household financial
reporting: reproducible Bronze → Silver → Gold transformation feeding read-only
analytics and a dashboard.

## Language

### Accounts and boundary

**Reporting boundary**:
The imported accounts, each with `ownership_scope` of `household` or
`person`. Only accounts inside it can hold a Transfer. Every other account is
external, including a household member's account that the household does not
import; money to or from it is income or expense, never a Transfer.
_Avoid_: Household accounts (ambiguous with `ownership_scope=household`),
transfer-eligible account (same set)

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
Pending and cancelled rows remain provenance. A booked transaction has one
type; its category reaches it through a Category allocation.
_Avoid_: Transaction in Bronze/Silver (too broad)

**Category allocation**:
A record that a stated amount of one Booked transaction belongs to one
category. It is the only way a category reaches a transaction, and the
allocations of a transaction always sum to its amount. A classified
transaction has exactly one for now; dividing a mixed purchase into several is
a later release.
_Avoid_: Split (the act, not the record), transaction category

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
`income` or `expense`. It is the only level that reaches a transaction, and it
reaches it through a Category allocation; a Category group never does.
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
Money returned against an earlier categorized movement. It nets against that
category in the originating measure, including a reversed fee or returned income.
_Avoid_: Reversal (ambiguous with Adjustment), chargeback (not distinct yet)

**Adjustment**:
An uncategorized correction, excluded from income and expense totals and
reported separately. A Refund carries a category and is not an Adjustment.

**Category group**:
The fixed top level of the two-level category hierarchy. It gathers related
categories of one direction for reporting and is never assigned to a
transaction directly.
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
The last date an account's imported exports are known to cover, computed from
its admitted exports by the formula in
[`docs/architecture/silver-layer.md`](docs/architecture/silver-layer.md#evidence-through).
_Avoid_: last import date (the export, not the import, bounds the evidence)

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
A file the bank produces for one account, covering a date range the operator
chose. Overlapping exports of the same account are normal.
_Avoid_: statement, dump

**Export date**:
The date the bank produced an export, from the filename suffix or declared at
import. It says when the file was made, not how far it reaches; the
late-booking window is counted from it.
_Avoid_: import date, range end

**Covers through**:
The last date one export's evidence reaches: the end of the range the operator
asked the bank for, declared at import. Distinct from the *export date*, so a
year of history exported today is not read as covering today. It falls back to
the export date only where that cannot reach past the payload's last reporting
period; see
[`docs/architecture/bronze-layer.md`](docs/architecture/bronze-layer.md).
_Avoid_: export range, to-date

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
as overlapping exports that disagree, a later export showing fewer repeated
transactions, a source that keeps stating a broken balance chain,
Classification rules that conflict, or Transfer legs that compete for the same
match. Every decision that settles a quarantine is raised by one, so none has
to be known about in advance.
_Avoid_: error, warning, conflict

**Manual decision**:
A recorded human ruling: it classifies a transaction, settles a Review item,
or voids an import run. It targets transactions by their identity and never
edits source data. It is an entry in the Decision log.
_Avoid_: Override, fix, edit

**Decision log**:
The append-only record of Manual decisions, each stamped with when the
platform accepted it. A decision is never edited or deleted; a later entry
supersedes or retracts it.
_Avoid_: Overrides file, decisions file (the log is not edited in place)

**Voided import run**:
An import run a person has declared mistaken, for example because it was
declared against the wrong account. Its raw payload is retained but it
contributes nothing downstream.
_Avoid_: deleted import, undone import

### Publications and history

**Publication**:
One complete, immutable build of Gold, holding its dimensions, facts, lineage,
and review items, built from one Recipe, with a fingerprint of that result. A
consumer reads exactly one at a time. The rules are in
[`publications.md`](docs/architecture/publications.md).
_Avoid_: Version, snapshot (a Monthly balance snapshot is a fact), release

**Recipe**:
The record of every input a Publication was built from: its import runs,
configuration snapshot, Decision log position, and code version. Rebuilding a
Recipe with the code version it names yields the same result.
_Avoid_: Manifest, lineage (lineage explains one fact, not a build)

**Current publication**:
The Publication reports show by default. A successful build becomes current at
once, and undo makes the previous one current again.
_Avoid_: Latest publication (an As-known-at view can be newer)

**As-was view**:
The Publication that was current at a given moment, shown exactly as it was
then.
_Avoid_: Historical report (ambiguous with As-known-at view)

**As-known-at view**:
A Publication built from only the import runs started by a given moment,
interpreted with today's configuration and decisions. It is never current.
_Avoid_: As-of report (ambiguous with As-was view)

### Operations

**Profile**:
One of `production`, `development`, or `test`: a configuration of the same
code that names every path the application touches. Every store records the
profile it belongs to. The rules are in
[`docs/architecture/operations.md`](docs/architecture/operations.md).
_Avoid_: environment (ambiguous with the Python environment), instance

**Household inputs**:
Everything the household authors: the account registry, category taxonomy,
and classification rules as edited files, and the decision and import logs,
which only the application appends to. With the export archive, they are
enough to rebuild every store.
_Avoid_: configuration (only part of it), settings

**Backup set**:
A snapshot of every store in a profile, with a copy of its household inputs
and a manifest, taken together. Development reads production only through
one.
_Avoid_: backup (when meaning a copy of one file), dump
