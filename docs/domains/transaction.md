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
- **Transfer:** movement between two accounts within the household reporting
  boundary; not spending or income. It needs matching evidence or a manual
  decision ([ADR-012](../decisions/ADR-012-transfer-evidence.md)). Money to or
  from an account the household does not import is income or expense.
- **Adjustment:** an uncategorized correction that needs an explanation. It
  carries no category, is excluded from income and expenses, and is reported
  separately.
- **Unknown:** valid imported record that nothing classified, or whose
  evidence conflicts or is ambiguous. It always has an open review item.

A transaction has exactly one type. Its category is not an attribute of the
transaction but a **category allocation**: a record that this transaction's
money belongs to that category. A classified transaction has exactly one
allocation, for its whole amount; dividing a mixed purchase into several is a
later release, and needs no change to what a transaction means
([ADR-008](../decisions/ADR-008-category-allocation-grain.md)).

Classification decides the type and the allocation together, for the whole
transaction: a manual decision first, then a transfer match, then rules
([ADR-011](../decisions/ADR-011-classification-precedence.md),
[`classification.md`](../architecture/classification.md)).

## Lifecycle

`source payload → Bronze record → Silver canonical transaction → Gold business
transaction`

No step mutates the record in the preceding layer. A corrected classification
is a new manual decision or rule change that Gold applies on the next build,
never a rewrite of the bank payload. Each build is a new publication, and
earlier ones stay explainable and viewable
([`publications.md`](../architecture/publications.md)).

## Identity and Deduplication

The importer must retain the bank/source identifier where supplied. When one is
absent, Silver derives the identifier by
[ADR-009](../decisions/ADR-009-transaction-identity.md): account, transaction
date, amount, identity text, and an occurrence number. It must not deduplicate
only by date and amount, and it must not include the source-record position,
which shifts between exports of the same transaction.
