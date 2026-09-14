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
- **Refund:** positive money returned against a prior purchase. It carries
  the same `category_id` as the purchase it reverses and nets against that
  category's spending rather than counting as income or disappearing from the
  report.
- **Transfer:** movement between accounts within the household reporting
  boundary; not spending or income.
- **Adjustment:** a correction, fee reversal, or exceptional entry with no
  originating purchase to net against. It needs explicit policy treatment,
  carries no category, and is excluded from income and expense totals.
- **Unknown:** valid imported record awaiting classification.

A transaction is classified as a whole: it has exactly one type and at most
one category, and it is never split across categories
([ADR-008](../decisions/ADR-008-single-category-per-transaction.md)).

## Lifecycle

`source payload → Bronze record → Silver canonical transaction → Gold business
transaction`

No step mutates the record in the preceding layer. A corrected classification
creates a new materialized Gold version or override history, not a rewrite of
the bank payload.

## Identity and Deduplication

The importer must retain the bank/source identifier where supplied. When one
is absent, Silver may generate a deterministic content fingerprint, including
source account, booking date, amount, description, and source-record position.
It must not deduplicate only by date and amount.
