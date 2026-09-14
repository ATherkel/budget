# ADR-004: Analytics Reads Gold Only

**Status:** Accepted

## Decision

Analytics, forecasting, APIs, and presentation depend on the versioned Gold
contract, not on Bronze, Silver, connectors, or CSV files.

## Consequences

- Gold contract changes require explicit versioning and migration planning.
- Analytics can be developed and tested in parallel using synthetic Gold
  fixtures.
