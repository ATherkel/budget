---
type: decisions
---
# ADR-020: Record Stage-Specific Build Provenance

**Status:** Accepted

This ADR records why Silver and Gold need separate, immutable build identity
and what Gold must preserve from the Silver result it consumed.

## Context

ADR-014 treated one application commit as the code version for a Gold recipe.
That is too narrow once Silver and Gold can diverge: Gold can be rebuilt from
an older stored Silver result, and a new Silver build can reuse the same
import-run identifiers. A recipe that names only those runs cannot tell which
Silver interpretation Gold consumed. It could also attribute today's decision
log or code to an older result that never read them.

Bronze records the declared source format and retains the exact payload bytes,
but it does not record the identity of the parser implementation that first
derived source records. Rebuilding from Bronze reparses with the installed
parser, so source format alone cannot identify historical parser output.

## Decision

- Silver commits its result, decoding currencies, completion marker and
  immutable provenance in one transaction. The exact fields, fingerprint and
  unknown-build rules are defined in
  [Silver build provenance](../architecture/silver-layer.md#build-provenance).
- Every new Gold recipe retains an immutable copy of the provenance Gold
  consumed, while recording Gold's own inputs and producer. Gold never
  rereads current Silver to explain an older publication or backfills a
  historical recipe.
- Gold publishes only after the acceptance checks in
  [Gold acceptance](../architecture/publications.md#gold-acceptance). Gold-only
  changes do not cause a Silver rebuild.
- Historical Bronze parser identity remains explicitly unknown until separate
  work records it. A current parser is never substituted for that identity.

## Consequences

- A changed Silver result with unchanged import-run identifiers produces a new
  Gold recipe and is not a no-op.
- Each recipe attributes the Silver interpretation consumed and the Gold
  interpretation applied to their separate stages.
- Unknown, stale, or incompatible Silver provenance remains readable where its
  stored shape permits, but it cannot authorize a new Gold publication.
- A consumed account removed from the account registry is a distinct refused
  input, not stale Silver provenance.
- Silver and Gold still commit separately. Each stage commits its result and
  provenance atomically, but a crash between stages leaves the previous Gold
  publication current until a retry completes the later stage.
- Dependency-lock capture, parser identity, and cross-parser replay remain
  separate work.

## Implementation Status

Status is anchored to the reviewed commit and tracked issues on the
[documentation entry page](../README.md#provenance-at-a-glance).
