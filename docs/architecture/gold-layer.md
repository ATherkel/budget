# Gold Layer

## Purpose

Represent financial business facts.

## Responsibilities

Classify:

- income
- expense
- transfer

Assign:

- categories
- account groups
- budget groups

## Output Contract

Gold data must remain stable even if source systems change.

## Example

```python
GoldTransaction(
    transaction_id: str,
    category: str,
    transaction_type: str,
    budget_group: str,
    reporting_period: str
)
```

## Consumers

- analytics
- forecasting
- dashboards

## Ownership

Gold Agent