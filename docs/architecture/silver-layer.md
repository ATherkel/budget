# Silver Layer

## Purpose

Convert source-specific data into a canonical model.

## Canonical Transaction

```python
Transaction(
    transaction_id: str,
    account_id: str,
    booking_date: date,
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

## Downstream Requirements

Gold relies on two guarantees that Silver must provide. [Issue #5](https://github.com/ATherkel/budget/issues/5)
defines how Silver provides them:

- a stable canonical identity for each transaction, from which Gold derives a
  `transaction_id` that survives rebuilds;
- a deterministic order of each account's transactions, including those
  sharing a booking date, so Gold can evaluate the balance chain.

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