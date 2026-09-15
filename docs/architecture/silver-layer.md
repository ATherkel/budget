# Silver Layer

## Purpose

Convert source-specific data into a canonical model.

## Canonical Transaction

```python
Transaction(
    transaction_id: str,
    account_id: str,
    booking_date: date,
    day_sequence: int,
    amount: Decimal,
    currency: str,
    description: str,
    source_system: str,
    balance: Decimal | None,
    source_status: str,
)
```

`balance` is the bank-stated account balance immediately after this
transaction, carried through verbatim; `source_status` is the source's own
booking status (e.g. completed vs. pending), also carried through verbatim.
Silver retains both as technical metadata — it does not interpret, reconcile,
or filter on them. Gold decides which rows are settled enough to materialize
and how the balance evidence is used.

`day_sequence` orders an account's transactions within one `booking_date`,
following the bank's own row order; the balance check depends on it, because
one day can hold many rows. When exports overlap, Silver merges their rows into
one order while deduplicating. It never reorders rows the bank listed.

Silver also passes forward each account's latest export date from Bronze
import-run metadata. Gold derives `GoldAccount.evidence_through` from it.

## Responsibilities

- schema normalization
- validation
- deduplication
- enrichment of technical metadata

## Non-Responsibilities

- categorization
- budgeting
- reporting

## Ownership

Silver Agent