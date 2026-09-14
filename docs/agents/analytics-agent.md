# Analytics Agent

## Mission

Produce reporting datasets from Gold data.

## Inputs

The versioned [Gold data contract](../architecture/gold-contract.md) through
its repository interface only.

## Forbidden Dependencies

- APIs
- CSV files
- Bronze tables
- Silver tables

## Deliverables

- Typed monthly, category, trend, and account-activity report DTOs.
- Tests using synthetic Gold fixtures only.
- Documentation of each measure, inclusion rule, and zero-denominator policy.

Transfers are excluded from income, expenses, and savings-rate calculations,
but may appear in account activity.

## Acceptance Criteria

A source-system replacement must not require any code changes. The module must
not import a connector, parser, raw-file path, or Bronze/Silver type.
