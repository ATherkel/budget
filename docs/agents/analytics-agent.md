# Analytics Agent

## Mission

Produce reporting datasets from Gold data.

## Inputs

The versioned [Gold data contract](../architecture/gold-contract.md) through
`GoldRepository` only: accounts, categories, transactions, category
allocations, and monthly balance snapshots.

## Forbidden Dependencies

- APIs
- CSV files
- Bronze tables
- Silver tables
- `GoldLineageRepository`

## Deliverables

- Typed monthly, category, trend, and account-activity report DTOs.
- Tests using synthetic Gold fixtures only.
- Documentation of each measure, inclusion rule, and zero-denominator policy.

Transfers are excluded from income, expenses, and savings-rate calculations,
but may appear in account activity. Coverage is read from Gold's monthly
balance snapshots, never recomputed.

## Acceptance Criteria

A source-system replacement must not require any code changes. The module must
not import a connector, parser, raw-file path, or Bronze/Silver type.
