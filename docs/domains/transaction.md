# Transaction Domain

A transaction is a booked monetary movement on an account. The source record
may contain more fields and different terminology; Gold expresses the stable
household interpretation.

A source row only becomes a transaction once its source marks it
completed/settled. A row still pending or unsettled is retained in Bronze and
Silver as provenance but does not become a Gold transaction until it settles;
the household must never see a pending amount presented as booked.

## Types

- **Income:** positive money received that contributes to household income.
- **Expense:** negative money spent that contributes to household spending.
- **Transfer:** movement between accounts within the household reporting
  boundary; not spending or income.
- **Adjustment:** a correction, fee reversal, or exceptional entry that needs
  explicit policy treatment. A refund against a prior purchase is an
  Adjustment that carries the same `category_id` as the purchase it reverses,
  netting against that category's spending rather than counting as income or
  disappearing from the report.
- **Unknown:** valid imported record awaiting classification.

## Lifecycle

`raw payload → Bronze source record → Silver canonical transaction → Gold
business transaction`

No step mutates the record in the preceding layer. A corrected classification
creates a new materialized Gold version or override history, not a rewrite of
the bank payload.

## Identity and Deduplication

The importer must retain the bank/source identifier where supplied. When one
is absent, identity follows ADR-007:

- The identifier is built from the account, booking date, amount,
  whitespace-normalized text, and an occurrence number among visibly identical
  transactions.
- When exports overlap, each group of identical transactions counts the
  highest number shown by any single export.
- Silver verifies the merge with the bank-stated balances.

A **duplicate** is the same transaction seen in more than one source record and
collapses to one. A **repeated transaction** is a distinct transaction that
merely looks identical to another and is always kept. Identity never depends
on row position across exports. Silver never deduplicates only by date and
amount, or by content alone.
