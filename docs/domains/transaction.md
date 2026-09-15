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
- **Transfer:** movement between two accounts within the household reporting
  boundary; not spending or income. It needs matching evidence or a manual
  decision ([ADR-010](../decisions/ADR-010-transfer-evidence.md)). Money to or
  from an account the household does not import is income or expense.
- **Adjustment:** a correction, fee reversal, or exceptional entry with no
  originating purchase to net against. It needs explicit policy treatment,
  carries no category, and is excluded from income and expense totals.
- **Unknown:** valid imported record awaiting classification: nothing
  classified it, or its evidence conflicts or is ambiguous. Every unknown
  transaction has an open review item.

A transaction is classified as a whole: it has exactly one type and at most
one category, and it is never split across categories
([ADR-008](../decisions/ADR-008-single-category-per-transaction.md)).
Classification comes from a manual decision, then a transfer match, then
classification rules ([ADR-009](../decisions/ADR-009-classification-precedence.md));
the policy is in [`classification.md`](../architecture/classification.md).

## Lifecycle

`source payload → Bronze record → Silver canonical transaction → Gold business
transaction`

No step mutates the record in the preceding layer. A corrected classification
is a new manual decision or rule change that Gold applies on the next build,
never a rewrite of the bank payload. How versions are kept is issue #8's
concern.

## Identity and Deduplication

The importer must retain the bank/source identifier where supplied. When one
is absent, Silver may generate a deterministic content fingerprint, including
source account, booking date, amount, description, and source-record position.
It must not deduplicate only by date and amount.
