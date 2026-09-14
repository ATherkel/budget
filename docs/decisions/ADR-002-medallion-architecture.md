# ADR-002: Use a Medallion Data Architecture

**Status:** Accepted

## Decision

Data moves through Bronze (source-preserving), Silver (canonical and
validated), Gold (household business facts), Analytics, and Presentation.
Each layer depends only on its immediate declared input contract.

## Consequences

- A bank or import-format change is confined to the early layers.
- The initial implementation has more explicit data boundaries than a direct
  CSV-to-dashboard prototype, in return for replacement and auditability.
