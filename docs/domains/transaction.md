# Transaction Domain

A transaction is a booked monetary movement on an account. The source record
may contain more fields and different terminology; Gold expresses the stable
household interpretation.

A source row only becomes a transaction once it is booked. Silver maps each
source's status to `booked`, `pending`, or `cancelled`:

- A **pending** row is retained in Bronze and Silver as provenance but is not
  a transaction; if a later export shows it booked, the booked row becomes
  one. The household must never see a pending amount presented as booked.
- A **cancelled** row (Danske `Slettet`, which carries no balance) never
  becomes a transaction. It is retained in Bronze and Silver as provenance
  and excluded from Gold and from the balance chain.

A transaction's date is its **transaction date**, the date the source assigns
to it. For Danske this is the purchase date, which can precede booking by
days. A late-booked transaction therefore lands in a period that may already
look finished, which is why periods stay provisional for a while after they
end.

## Types

- **Income:** positive money received that contributes to household income.
- **Expense:** negative money spent that contributes to household spending.
- **Refund:** money returned against an earlier categorized movement. It
  carries that movement's category and nets against its measure: positive
  for an expense category (including reversed fees), negative for returned
  income in an income category.

- **Transfer:** movement between accounts within the household reporting
  boundary; not spending or income.
- **Adjustment:** an uncategorized correction that needs an explanation. It
  carries no category, is excluded from income and expenses, and is reported
  separately.

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
