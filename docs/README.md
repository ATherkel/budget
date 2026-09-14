# Documentation Map

This directory is the project contract before implementation begins. Documents
are deliberately split by concern so work can be delegated without giving an
agent authority outside its boundary.

## Start Here

1. Read [the vision](00-vision.md), [principles](01-principles.md), and
   [architecture](02-architecture.md).
2. Read [the roadmap](03-roadmap.md) to identify the current phase.
3. For implementation work, read the relevant layer contract and domain
   documents, then the matching agent brief.

## Normative Documents

- `architecture/gold-contract.md` is the public data contract for analytics,
  forecasting, and presentation. Downstream code must not depend on Bronze or
  Silver storage or types.
- `domains/` defines business meaning. It takes precedence over an individual
  layer document when there is a conflict.
- `decisions/` records accepted architectural decisions. Changes require a new
  ADR; do not silently revise a decision to fit an implementation.

## Conventions

- Dates and times use ISO 8601. Monetary values use decimal arithmetic, never
  binary floating point.
- Source payloads and raw imported files are retained. Derived layers are
  rebuildable.
- A module may depend only on its declared input contract. It must not reach
  around the contract to read an upstream layer.
