# Budget Platform Vision

## Goal

Build a household financial platform that provides a complete view of:

- spending
- income
- transfers
- budgets
- savings
- forecasts

across all current and future financial institutions.

The platform must remain independent of any specific bank.

## Key Requirement

Analytics and reporting must not depend on transaction source systems.

A bank change should not require modifications to analytics, dashboards, forecasts, or business logic.

## Design Philosophy

The platform is a data platform first and a web application second.

The source of truth is transaction data.

All metrics are reproducible from stored transactions.

No report is a system of record.

## Success Criteria

- New banks can be added without changing analytics.
- Historical data remains available forever.
- All transformations are traceable.
- Reports are reproducible.
- Mobile-first experience.
- Self-hostable.