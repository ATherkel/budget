---
type: glossary
---
# Household Finance

The vocabulary of a platform that turns imported bank exports into
trustworthy household reporting, through a reproducible Bronze → Silver → Gold
pipeline feeding read-only analytics. Each term is defined in a line or two
and links to the doc that owns its rules.

## Language

### Accounts and boundary

**Reporting boundary**:
The imported accounts (`ownership_scope` `household` or `person`). Only they
can hold a Transfer; money to or from any other account, a member's unimported
one included, is income or expense.
_Avoid_: Household accounts (ambiguous with `ownership_scope=household`),
transfer-eligible account (same set)

**Managed period**:
The reporting months an account is part of the household's history: from its
first Booked transaction to the month it closes, or while open, the latest
published month ([`gold-contract.md`](architecture/gold-contract.md#monthlybalancesnapshot)).
_Avoid_: Active period, account lifetime (the bank account may predate the
household's data)

### Transactions and classification

**Booked transaction**:
A transaction whose source row Silver maps to `booking_status=booked`; pending
and cancelled rows stay provenance.
_Avoid_: Transaction in Bronze/Silver (too broad)

**Category allocation**:
The record that an amount of one Booked transaction belongs to one Category;
the only way a category reaches a transaction
([ADR-008](decisions/ADR-008-category-allocation-grain.md)).
_Avoid_: Split (the act, not the record), transaction category

**Classification**:
A booked transaction's type and, for income, expense or Refund, its Category,
from a Manual decision, a matched Transfer or a Classification rule
([`classification.md`](architecture/classification.md#precedence)).
_Avoid_: Categorisation (narrower), tagging

**Classification rule**:
A household-authored pattern over one transaction's own facts that assigns a
Category, claims a Transfer leg, or marks an Adjustment
([`classification.md`](architecture/classification.md#classification-rules)).
_Avoid_: Mapping, filter

**Category**:
A household-defined heading for income or spending, with a direction
([`classification.md`](architecture/classification.md#taxonomy)).
_Avoid_: Bank category (a different thing)

**Category group**:
The top level of the two-level hierarchy, gathering categories of one
direction; never assigned to a transaction.
_Avoid_: Parent category, super-category

**Bank category**:
The label a bank puts on its export rows: provenance a rule may test, never a
Category by itself.
_Avoid_: Category, when meaning the bank's label

**Transfer**:
Money moved between two accounts inside the Reporting boundary, as two legs,
or one-sided by Manual decision
([`classification.md`](architecture/classification.md#transfer-matching)).
_Avoid_: Internal transfer (redundant), movement

**Refund**:
Money returned against a categorized movement, netting against that category.
_Avoid_: Reversal (ambiguous with Adjustment), chargeback (not distinct yet)

**Adjustment**:
An uncategorized correction, reported apart from income and expenses.

**Unclassified money**:
Money on `unknown` transactions, reported as money in, money out and a count,
so opposite amounts never cancel.
_Avoid_: Unclassified total (a single sum hides offsetting amounts)

### Balances and trust

**Balance chain**:
Each transaction's bank-stated balance checked against the last known balance
plus every amount since; a break or missing balance shows in Coverage, never
corrected ([`gold-layer.md`](architecture/gold-layer.md#balance-chain-evaluation)).

**Coverage**:
Whether the balance evidence covers a whole account-month: `complete`,
`partial` or `no_data` ([`gold-layer.md`](architecture/gold-layer.md#coverage)).
Absent evidence is never zero.

**Evidence range**:
A stretch of days an account's admitted exports are declared to cover
([`silver-layer.md`](architecture/silver-layer.md#evidence-ranges)).
_Avoid_: coverage (that is Gold's per-period status)

**Evidence through**:
The last day of an account's latest Evidence range.
_Avoid_: last import date (the export, not the import, bounds the evidence)

**Late-booking window**:
How many days after a month ends an export must be produced to settle the
month's late bookings, 7 by default
([`gold-layer.md`](architecture/gold-layer.md#late-bookings-settled)).

**Monthly balance snapshot**:
One account's opening and closing balance and Coverage for one month of its
Managed period ([`gold-contract.md`](architecture/gold-contract.md#monthlybalancesnapshot)).
_Avoid_: Statement (a bank document), balance on its own (ambiguous with the
bank-stated balance after one transaction)

**Provisional period**:
A period that includes the current month or still awaits exports past the
late-booking window
([`presentation-layer.md`](architecture/presentation-layer.md#data-trust-display)).

### Imports and identity

**Export**:
A file the bank produces for one account over a range the operator chose;
overlaps are normal.
_Avoid_: statement, dump

**Export date**:
When the bank produced an export, not how far it reaches.
_Avoid_: import date, range end

**Covers from** / **Covers through**:
The inclusive range the operator declared for an export, never inferred and
never past its Export date ([`bronze-layer.md`](architecture/bronze-layer.md)).
_Avoid_: export start, from-date, export range, to-date

**Transaction date**:
The date the source gives a transaction (Danske: the purchase date); it sets
the reporting period.
_Avoid_: booking date, value date

**Late booking**:
A transaction booked days after its date, so it first appears in a later export
on a date an earlier one covered.
_Avoid_: back-dated transaction, missing transaction

**Raw payload**:
The exact bytes received from a source, never altered.
_Avoid_: raw data, original file

**Import run**:
One presentation of a raw payload, with the account the operator declared.
_Avoid_: import, load, upload

**Source record**:
One record as the source presented it, uninterpreted.
_Avoid_: raw row, line

**Unbooked record**:
A source record not booked, such as pending or deleted; kept as provenance.
_Avoid_: pending transaction, deleted transaction, cancelled transaction

**Duplicate**:
One booked transaction in several source records, collapsed to one.
_Avoid_: repeat, copy

**Repeated transaction**:
One of several distinct, identical-looking booked transactions; each is kept.
_Avoid_: duplicate

**Cross-account duplicate**:
One payload in the inbox under two or more accounts at once; all its files are
refused ([`operations.md`](architecture/operations.md#failure-and-retry)).
_Avoid_: duplicate (that is Silver's collapse of one booked transaction),
account conflict

**Duplicate incident**:
One Cross-account duplicate as an import reports it: its group of files.
_Avoid_: duplicate, incident on its own

**Dropped transaction**:
An admitted transaction a later export covering its date no longer shows; a
person decides whether the bank removed or reworded it
([ADR-017](decisions/ADR-017-dropped-transactions.md)).
_Avoid_: missing transaction (reads as a Late booking), deleted transaction

### Review

**Quarantine**:
An import run retained but contributing nothing, having failed validation or
awaiting review.
_Avoid_: rejected, held, failed import

**Review item**:
An ambiguity a person must decide, such as a Dropped transaction or
conflicting rules; every quarantine a decision can settle raises one.
_Avoid_: error, warning, conflict

**Handle**:
A unique prefix, at least 8 characters, of a transaction's ID that a Manual
decision accepts ([`operations.md`](architecture/operations.md#commands)).
_Avoid_: transaction ID (the full identity), truncated ID without uniqueness

**Manual decision**:
A recorded human ruling on a transaction, Review item or import run, never
editing source data; an entry in the Decision log.
_Avoid_: Override, fix, edit

**Decision log**:
The append-only record of Manual decisions; a later entry supersedes or
retracts an earlier one
([`publications.md`](architecture/publications.md#the-decision-log)).
_Avoid_: Overrides file, decisions file (the log is not edited in place)

**Voided import run**:
An import run a person declared mistaken; retained, contributing nothing.
_Avoid_: deleted import, undone import

### Publications and history

**Publication**:
One complete, immutable Gold build from one Recipe; consumers read one at a
time ([`publications.md`](architecture/publications.md)).
_Avoid_: Version, snapshot (a Monthly balance snapshot is a fact), release

**Recipe**:
The record of every input a Publication consumed
([`publications.md`](architecture/publications.md#the-recipe)).
_Avoid_: Manifest, lineage (lineage explains one fact, not a build)

**Silver build provenance**:
What Silver commits with a result to identify its inputs, output and producer
([`silver-layer.md`](architecture/silver-layer.md#build-provenance)).
_Avoid_: Silver metadata (hides the atomicity and identity contract), current
context

**Fresh**, **Stale** and **Unknown Silver provenance**:
Whether that provenance matches what Gold would use, no longer matches, or
cannot be established
([Gold acceptance](architecture/publications.md#gold-acceptance),
[recovery](architecture/operations.md#provenance-recovery)).
_Avoid_: Current Silver, latest Silver, missing Silver, old publication

**Undeclared consumed account**:
An account a consumed Silver run names that `accounts.toml` no longer declares
([recovery](architecture/operations.md#provenance-recovery)).
_Avoid_: Stale account, stale Silver

**Current publication**:
The Publication reports show by default; a build becomes current at once, and
undo restores the previous one.
_Avoid_: Latest publication (an As-known-at view can be newer)

**As-was view**:
The Publication current at a given moment, exactly as it was.
_Avoid_: Historical report (ambiguous with As-known-at view)

**As-known-at view**:
A new Publication from only the import runs started by a moment, with today's
interpretation; never current.
_Avoid_: As-of report (ambiguous with As-was view)

**Legacy publication**:
A labeled Publication a Gold migration could not convert, kept in its old
schema ([`operations.md`](architecture/operations.md#legacy-publications)).
_Avoid_: archived publication, old version

### Operations

**Profile**:
`production`, `development` or `test`: a configuration of the same code naming
every path ([`operations.md`](architecture/operations.md#profiles)).
_Avoid_: environment (ambiguous with the Python environment), instance

**Household inputs**:
Everything the household authors or declares, as text: registries, rules, and
the decision and import logs
([`operations.md`](architecture/operations.md#household-inputs)).
_Avoid_: configuration (only part of it), settings

**Backup set**:
A snapshot of every store in a profile, with its inputs and a manifest;
development reads production only through one
([`operations.md`](architecture/operations.md#backup-and-restore)).
_Avoid_: backup (when meaning a copy of one file), dump
