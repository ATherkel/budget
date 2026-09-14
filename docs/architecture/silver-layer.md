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
    source_system: str
)
```

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