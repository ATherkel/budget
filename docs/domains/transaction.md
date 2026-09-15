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
- **Transfer:** movement between accounts within the household reporting
  boundary; not spending or income.
- **Adjustment:** an entry that breaks the income/expense sign convention.
  The definition is structural:
  - An adjustment with a `category_id` is a **refund**. It nets against that
    category (spending for an expense category, income for an income
    category) rather than counting as income or disappearing from the
    report. A reversed bank fee is a refund against the bank-fees category.
  - An adjustment without a `category_id` is a correction. It is excluded
    from income and expenses and reported on its own line
    (`analytics-layer.md`).
- **Unknown:** valid imported record awaiting classification.

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
