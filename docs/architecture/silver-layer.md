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
    booking_status: Literal["booked", "pending", "cancelled"],
)
```

`balance` is the bank-stated account balance immediately after this
transaction, carried through verbatim. Silver does not reconcile it; how the
balance evidence is used is decided downstream (ADR-006).

`booking_status` is Silver's normalization of the source's own status. Each
source format maps its status values to `booked`, `pending`, or `cancelled`;
for Danske, `Udført` is `booked` and `Slettet` is `cancelled`. An unmapped
status value is a validation error, and the original value stays in Bronze.
Gold therefore never needs a bank's status vocabulary: it materializes `booked`
rows only.

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