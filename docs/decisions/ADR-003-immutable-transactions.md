# ADR-003: Retain Immutable Source Data

**Status:** Accepted

## Decision

Persist each imported source payload and import provenance without overwriting
it. Silver and Gold are rebuildable derived data. Corrections are modeled as
new transformation/override history, not destructive edits to bank data.

## Consequences

- Import bugs and changed rules can be corrected reproducibly.
- Storage, retention, and privacy controls must be designed before deployment.
