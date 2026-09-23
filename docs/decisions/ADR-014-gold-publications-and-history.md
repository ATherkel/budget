# ADR-014: Publish Gold as Immutable Publications, with Recipes and a Decision Log

**Status:** Proposed

## Context

Principle 3 says Gold is reproducible from Silver. It is not: a Gold build
also reads the account registry, the category taxonomy, the classification
rules, the manual decisions, the transfer matching policy, and the code that
implements them. Each can change, and each change restates history, because
every dimension is Type 1 ([ADR-007](ADR-007-dimensional-gold-model.md)).
ADR-007 deferred reproducing a report exactly as it was read, and ADR-013
deferred how a build is published while the dashboard reads. Contract
invariant 15 says a consumer reads one publication, but nothing yet defines
one. Raised in [issue #8](https://github.com/ATherkel/budget/issues/8).

The maintainer chose four things:

- past reports in two forms: *as-was*, meaning exactly what was shown at a
  moment, and *as-known-at*, meaning the data known at a moment under today's
  interpretation;
- keep every recipe, and keep results only for the current publication, the
  previous one, and labeled ones;
- a successful build becomes current immediately, with a printed diff and a
  one-step undo;
- manual decisions in an append-only log.

## Decision

- **A publication is one complete, immutable Gold build**, identified by an
  increasing `publication_id`. Every Gold table is keyed by it, and every
  consumer read is confined to one. Facts do not carry it;
  `GoldRepository.publication()` does.
- **Every publication has a recipe.** It names the import runs, a
  content-addressed configuration snapshot, a decision-log position, the code
  version, and a fingerprint of the result. Recipes are kept forever.
- **The build is a pure function of its recipe.** It never reads the clock.
  `built_at` is metadata outside the fingerprint, and anything that depends on
  today's date is computed when a report is read. The same recipe with the
  same code yields the same fingerprint. A production build refuses to run
  when it cannot name its code version.
- **Promotion is immediate.** A successful pipeline build becomes current in
  the same write transaction that stores it. The CLI prints the diff against
  the previous current publication. `undo` moves the pointer back, and the
  pointer history records every move. A build whose recipe equals the current
  one publishes nothing.
- **Retention.** Results are kept for the current publication, the previous
  one, and every labeled one. Any other result can be re-created by replaying
  its recipe with the code it names.
- **Past views are publications too, built by the CLI.** An as-was view is the
  publication current at D, either retained or replayed and checked against
  its fingerprint. An as-known-at view is a new publication built from the
  import runs started by D under today's interpretation, and it can never
  become current. The dashboard stays read-only and opens any retained
  publication.
- **Manual decisions are an append-only log.** Each entry carries a
  platform-set `recorded_at`, and a new entry supersedes an old one instead of
  editing it. Rules, the taxonomy, the account registry, and the matching
  policy remain edited files, versioned through the recipes' configuration
  snapshots.
- **No Type 2 dimensions.** As-was views give exact history, which is why
  ADR-007 chose Type 1.

The policy, the recipe's parts, and the synthetic scenarios are in
[`publications.md`](../architecture/publications.md).

## Considered Options

- **Current only.** Rejected: the household could explain a past report but
  not see it again.
- **Bitemporal columns on every fact** (valid and recorded time, queried as
  of any moment). Rejected: every consumer query would carry two time
  predicates. Building a view as a separate publication gives the same answers
  and leaves the contract's queries unchanged.
- **Type 2 dimensions.** Rejected: they preserve what a category was called,
  not how a transaction was classified (ADR-007).
- **Keep every result.** Rejected: storage and backups grow with every import,
  and every Gold migration must carry all of them, while recipes already make
  them reproducible.
- **Recipes only, no retained previous result.** Rejected: undo would need a
  rebuild at the moment something just went wrong.
- **Hold each build as a candidate until the operator promotes it.**
  Rejected: an extra command on every import. The diff and a one-step undo
  catch the same mistakes, because the previous result is retained.
- **Decision files edited in place, versioned only through snapshots.**
  Rejected by the maintainer: the append-only log gives an audit trail
  independent of builds, and a validation boundary a browser editor can
  reuse.
- **One database file per publication.** Rejected: more files to place, back
  up, and migrate. With every table keyed by `publication_id` in the one
  store, the pointer moves in one SQLite transaction (ADR-013).

## Consequences

- Principle 3 now reads: Gold is reproducible from its recipe, not from Silver
  alone.
- The Gold contract gains `GoldPublication`, `GoldPublications`, and
  `GoldRepository.publication()`. Invariant 15 points here.
  `classification_version` in lineage is the fingerprint of the configuration
  snapshot and the effective classification decisions.
- Silver becomes a function of a set of import runs, so an as-known-at view
  can derive it from a subset. Silver stays one current state for pipeline
  builds, and views derive theirs in a scratch area.
- ADR-011's "two decisions on one transaction" becomes a rejection when the
  second entry is recorded, not only a build error.
- ADR-013 allows a Gold-only schema change to drop and rebuild Gold tables.
  Those tables now also hold the retained results, so such a migration either
  converts them or deletes them. Recipes survive either way. A deleted result
  from an older contract version can be replayed only with its own code
  version, in a separate store.
- A recipe is only replayable while its code version can still run. A
  publication that must outlive its code is labeled, so its result is kept.
- The dashboard needs a publication picker and a banner for non-current
  publications (issue #11). Every page pins one publication across its
  requests.
- Issue #10 defines the commands, the decision log's format, and where each
  profile's publications live.
- Resolves [issue #8](https://github.com/ATherkel/budget/issues/8) once
  accepted.
