---
type: decisions
---
# ADR-020: Record Stage-Specific Build Provenance

**Status:** Accepted

## Context

ADR-014 treated one application commit as the code version for a Gold recipe.
That was no longer accurate once Silver and Gold could diverge: Gold could be
rebuilt from an older stored Silver result, and a new Silver build could reuse
the same import-run identifiers. The recipe also named runs without identifying
the complete Silver result that Gold consumed.

As a result, a Gold rebuild could call stale Silver current merely because the
run identifiers were unchanged. It could also attribute today's decision log
and code to an older Silver result that did not consume them.

## Decision

A completed Silver build commits its result and one immutable provenance value
in one Silver transaction. That value records:

- the versioned fingerprint scheme and fingerprint of the complete Silver
  result plus its consumed currency projection;
- every stored and repeated import run Silver interpreted, with its payload
  identifier, retained as an immutable Bronze reference rather than a copy of
  the run's metadata;
- the exact account-currency projection for accounts named by those runs,
  including a run later voided by a decision;
- the typed effective Silver decisions;
- the complete decision-log position and prefix hash consumed;
- Silver's application commit when known and its identity-contract version; and
- an explicit `unknown` Bronze parser-provenance marker.

Every replacement commits a completion row. A direct store replacement without
supplied provenance records a completed but explicitly unknown context; absence
of the completion row still means Silver was never built. Migration from a
pre-provenance Silver schema clears derived rows, because today's inputs and
code cannot reconstruct what the old build consumed.

Gold retains in its recipe an immutable copy of the Silver fingerprint, run
references, consumed currencies, effective Silver decisions, log-prefix
evidence and Silver producer identity. Each run reference is its Bronze
identifier and payload hash, not a second copy of mutable or descriptive run
metadata. Gold's own code version remains the recipe's Gold producer version.
Historical recipes keep their missing Silver provenance explicit and are never
backfilled.

Before a new Gold publication, Gold validates that the recorded decision-log
prefix is still a prefix, the current effective Silver decisions equal those
consumed, the stored fingerprint scheme and Silver identity contract are
supported, and currencies for exactly the consumed projection still match. A
failure refuses before publication and directs the operator to
`budget rebuild --from silver`. Appending Gold-only decisions or adding an empty
account does not require a Silver rebuild.

## Consequences

- A changed Silver result with unchanged import-run identifiers produces a
  different Gold recipe and cannot be treated as a no-op.
- Each Gold recipe names the Silver interpretation and Gold interpretation it
  consumed instead of copying one current code version across stages.
- Legacy Silver and Gold state is readable when possible but cannot authorize a
  new publication without an explicit Silver rebuild.
- Dependency-lock capture remains separate work.
- This decision does not claim full replayability of historical Silver. Bronze
  parser provenance is explicitly unknown in this intermediate contract;
  parser capture, replay and recovery remain in the later #326 boundary.
