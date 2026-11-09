---
type: overview
---
# Documentation Map

This directory is the project contract before implementation begins. Documents
are deliberately split by concern so work can be delegated without giving an
agent authority outside its boundary.

## Start Here

1. Read [the vision](00-vision.md), [principles](01-principles.md), and
   [architecture](02-architecture.md).
2. Read [the roadmap](03-roadmap.md) to identify the current phase.
3. For implementation work, read the relevant layer contract and domain
   documents, then the matching agent brief. For behavior-changing application
   work, also follow the [test-driven development workflow](agents/tdd.md).
   All Python code must pass the [code quality gate](agents/code-quality.md).

## Provenance at a Glance

Silver build provenance is the immutable account of what produced a stored
Silver result. Gold must remember the exact result it consumed because a
rebuild can follow changed or reparsed Silver. Without that record, Gold could
mistake today's decisions, currencies, or producer for the context behind an
older publication.

Silver commits its result, decoding currencies, completion marker, and
provenance in one transaction. The exact fields and fingerprint are in
[Silver build provenance](architecture/silver-layer.md#build-provenance).
Gold copies the consumed provenance into each recipe; acceptance and retention
rules are in [Gold acceptance](architecture/publications.md#gold-acceptance)
and [The Recipe](architecture/publications.md#the-recipe). If a consumed
account is missing, declare it again with `closed_on` where appropriate;
rebuilding Silver cannot repair that declaration. Rebuild Silver for stale
context, then retry Gold. Gold-only changes need no Silver rebuild.

At reviewed main `8e2bc58d4e0721b4c4c8a3002b9c8ed8c422da4a` (2026-11-08), the Silver fingerprint
([#369](https://github.com/ATherkel/budget/issues/369)) and unavailable-review
handling ([#368](https://github.com/ATherkel/budget/issues/368)) are
implemented. Atomic provenance persistence
([#370](https://github.com/ATherkel/budget/issues/370)), decision-prefix
checking ([#371](https://github.com/ATherkel/budget/issues/371)), currency
freshness ([#372](https://github.com/ATherkel/budget/issues/372)), and Gold
recipe capture ([#373](https://github.com/ATherkel/budget/issues/373)) are
pending. Until they land, commands do not perform the complete checks
described here.

To reproduce history, use the retained result or replay the exact consumed
Silver with the recipe's Gold inputs and producer. A recipe alone does not
reconstruct missing historical Silver, and Bronze parser identity remains
unknown. Recovery is in [Provenance recovery](architecture/operations.md#provenance-recovery);
terms are in [the glossary](CONTEXT.md#publications-and-history).

## Normative Documents

- `architecture/gold-contract.md` is the public data contract for analytics
  and forecasting. Downstream code must not depend on Bronze or Silver storage
  or types.
- `architecture/report-contract.md` is the contract between analytics and
  presentation: the report context and the reports analytics returns.
  Presentation never reads Gold.
- `domains/` defines business meaning. It takes precedence over an individual
  layer document when there is a conflict.
- `domains/category-changes.md` is an append-only record rather than a
  definition: because the category dimension carries only the current
  interpretation, it logs when the taxonomy changed and why, so a decision
  taken on an older report can still be read.
- `architecture/publications.md` defines what one Gold build is, which one a
  report reads, what is kept of past builds, and what reproducible promises.
- `architecture/operations.md` says how the household runs the pipeline:
  profiles, stores, input file formats, commands, and backup and restore.
- `decisions/` records accepted architectural decisions. Changes require a new
  ADR; do not silently revise a decision to fit an implementation.
- `architecture/data-maps/` holds one logical data map per source format and
  target layer: for every target column, its source and transformation. A map
  restates its layer contract column by column and decides what the contract
  leaves open, marking those rows *Map decision*. It is normative where the
  contract is silent; on a conflict, the layer contract, `decisions/` and
  `domains/` win.

## Explanatory Documents

`primers/` holds standalone pages that explain a decision cluster to a reader
who has to live with it, rather than to an implementer. They are **not
normative**: a primer never decides anything, and where one disagrees with a
document under `architecture/` or `decisions/`, that document wins and the
primer is stale.

- [`primers/overlapping-exports-primer.html`](primers/overlapping-exports-primer.html)
  — why overlapping bank exports are hard, in fourteen modules with worked
  examples: transaction identity, the balance chain, whole-file admission, the
  manual decisions, coverage, the provisional label, and a worked case of a
  written-down rule that was wrong until it was run. Open it by
  double-clicking; it needs no server and stores progress in the browser only.
  It loads its fonts from Google Fonts and falls back to system fonts offline.
- [`primers/dimensional-gold-primer.html`](primers/dimensional-gold-primer.html)
  — what shape Gold hands household facts to a dashboard, in fourteen modules
  with worked examples: business processes and declared grain, the category
  allocation fact, the three conformed dimensions and how immutable keys plus
  a change log keep Type 1 history-safe, monthly balance snapshots,
  semi-additive balances, the balance chain and coverage, the `refund` type,
  and the split between the consumer and lineage interfaces. It closes with
  what the original grilling on issue #6 got wrong or left open, and what the
  owner decided once they read it. Open it by double-clicking; it needs no
  server and stores progress in the browser only. It loads its fonts from
  Google Fonts and falls back to system fonts offline.
- [`primers/classification-transfers-primer.html`](primers/classification-transfers-primer.html)
  — how each transaction gets its household meaning, in thirteen modules:
  the reporting boundary, rules and priority, transfer evidence, manual
  decisions, and review items. Opens and stores progress like the others.
- [`primers/publications-history-primer.html`](primers/publications-history-primer.html)
  — which version of Gold a report shows, in twelve modules following one
  February through five builds and three views: publications and double
  counting, the recipe and its fingerprint, undo, the two time axes behind
  as-was and as-known-at views, retention, the decision log, and which
  identifiers survive a rebuild. It closes with what the owner chose on
  issue #8 and what was chosen for them. Opens and stores progress like the
  others.
- [`primers/operations-primer.html`](primers/operations-primer.html) — how
  the household runs the pipeline, in thirteen modules: profiles, one store
  per ETL step, development from backups, the inputs folder and its formats,
  the monthly import, publishing into one Gold store and legacy
  publications, backup and restore, and what is left to check. Opens and
  stores progress like the others.

## Vocabulary

[`CONTEXT.md`](CONTEXT.md) is the household finance glossary: tight,
opinionated term definitions. It defines terms only and links to the governing
document for each rule; where they seem to differ, the governing document wins.

## Conventions

- Dates and times use ISO 8601. Monetary values use decimal arithmetic, never
  binary floating point.
- Source payloads and raw imported files are retained. Derived layers are
  rebuildable.
- A module may depend only on its declared input contract. It must not reach
  around the contract to read an upstream layer.
- Every Markdown file here opens with the Open Knowledge Format header that
  [ADR-019](decisions/ADR-019-open-knowledge-format-headers.md) sets out.
- A document cites another by linking the section, such as
  `[operations.md, *Stores*](architecture/operations.md#stores)`, and quoting
  the words it relies on. A section link survives edits around it, where a line
  number drifts with every one; renaming a heading means updating the links to
  it.
