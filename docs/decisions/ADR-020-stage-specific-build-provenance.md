---
type: decisions
---
# ADR-020: Record Stage-Specific Build Provenance

**Status:** Accepted

## Context

ADR-014 treated one application commit as the code version for a Gold recipe.
That is too narrow once Silver and Gold can diverge: Gold can be rebuilt from
an older stored Silver result, and a new Silver build can reuse the same
import-run identifiers. A recipe that names only those runs cannot tell which
Silver result Gold actually consumed. It can also attribute today's decision
log and code to an older Silver result that never read them.

Bronze records the declared source format and retains the exact payload bytes,
but it does not record the identity of the parser implementation that first
derived source records. Rebuilding from Bronze deliberately reparses with the
installed parser for each declared format. That can produce a new Silver result
from unchanged runs, so source-format selection alone is not parser provenance.

## Decision

A completed Silver build commits its result and one immutable provenance value
in one Silver transaction. The provenance value records:

- the versioned fingerprint scheme and fingerprint of the complete Silver
  result together with the consumed account-currency projection;
- every stored and repeated import run Silver interpreted, represented by its
  immutable Bronze reference: import-run identifier, payload hash, and
  declared account;
- the exact account-currency projection for accounts named by those runs,
  including an account whose run was later voided by a decision;
- the effective typed Silver decisions;
- the decision-log position and prefix hash consumed;
- the actual Silver producer commit when the profile records one, and the
  Silver identity-contract version; and
- an explicit `unknown` Bronze parser-provenance marker.

Every replacement commits a completion row as well. A direct store replacement
without supplied provenance is complete but explicitly unknown. Absence of the
completion row means Silver has never been built. A migration from a
pre-provenance Silver schema clears its derived result because today's inputs
cannot establish what the old result consumed.

Gold retains an immutable copy of the Silver provenance in every new recipe. It
also records its own producer commit, configuration snapshot, late-booking
window, and the position and prefix it consumed from the shared Decision log.
Effective Gold decisions are derived from the complete log entries through
that position. Gold never rereads mutable Silver metadata to explain an older
publication. Historical recipes keep their missing Silver provenance explicit
and are never backfilled from the checkout that happens to read them later.

Before a new Gold publication, Gold validates that the recorded Silver
decision-log prefix is still a prefix of the current log, the current effective
Silver decisions equal those Silver consumed, the stored fingerprint and
identity-contract schemes are supported, and currencies for exactly the
consumed run accounts still match. A consumed account missing from
`accounts.toml` is refused input (exit 3) and named; declaring it again is the
repair, and a Silver rebuild cannot supply the missing declaration. Unknown,
incompatible, or stale Silver provenance is a refused environment (exit 4);
stale provenance names `budget rebuild --from silver`. A Gold-only decision or
an added empty account does not require a Silver rebuild.

## Consequences

- A changed Silver result with unchanged import-run identifiers produces a
  different Gold recipe and cannot be treated as a no-op.
- Each recipe names the Silver interpretation Gold consumed and the Gold
  interpretation Gold applied instead of copying one current code version
  across both stages.
- Unknown, stale, or incompatible Silver provenance remains readable where its
  stored shape permits, but it cannot authorize a new Gold publication.
- A consumed account removed from the account registry is a distinct refused
  input, not stale Silver provenance. It must be declared again, with
  `closed_on` when appropriate.
- Silver and Gold still commit separately. Each stage commits its result and
  provenance atomically, but a crash between stages leaves the previous Gold
  publication current until a retry completes the later stage.
- Dependency-lock capture is separate work.
- Parser identity and cross-parser replay remain separate work. Silver can say
  that Bronze parser provenance is unknown; it must not represent the parser
  currently installed as the one that produced older source records.
- The provenance completion row and Gold recipe capture are part of this
  accepted contract. Where the running implementation has not yet supplied
  them, the absence is an explicit implementation gap rather than evidence
  that the missing values can be inferred.

## Implementation Status

The baseline branch already provides the versioned Silver result fingerprint,
an atomic Silver result-and-currency replacement, Bronze reparse, and atomic
per-store writes. It does not yet persist a Silver provenance completion row
or copy one into a Gold recipe. The architecture documents therefore describe
the accepted completed contract and mark this gap where it affects current
commands.
