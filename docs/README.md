---
type: overview
---
# Documentation Map

This directory is the project's contract, split by concern so work can be
delegated without authority outside its boundary.

## Start Here

1. Read [the vision](00-vision.md), [principles](01-principles.md), and
   [architecture](02-architecture.md).
2. Read [the roadmap](03-roadmap.md) to identify the current phase.
3. For implementation work, read the relevant layer contract and domain
   documents. For behavior-changing application work, also follow the
   [test-driven development workflow](agents/tdd.md). All Python code must
   pass the [code quality gate](agents/code-quality.md).

## Provenance at a Glance

Silver build provenance records exactly what produced a stored Silver result,
so Gold never mistakes today's decisions, currencies or producer for those
behind an older publication. Its fields are in
[Silver build provenance](architecture/silver-layer.md#build-provenance); when
Gold may publish, in [Gold acceptance](architecture/publications.md#gold-acceptance);
what to do when it refuses, in
[Provenance recovery](architecture/operations.md#provenance-recovery); terms,
in [the glossary](CONTEXT.md#publications-and-history).

## Normative Documents

- `architecture/gold-contract.md` is the public data contract for analytics
  and forecasting. Downstream code must not depend on Bronze or Silver storage
  or types.
- `architecture/report-contract.md` is the contract between analytics and
  presentation: the report context and the reports analytics returns.
  Presentation never reads Gold.
- `domains/` defines business meaning. It takes precedence over an individual
  layer document when there is a conflict.
- `domains/category-changes.md` is an append-only log of taxonomy changes and
  why, since the category dimension carries only the current interpretation.
- `architecture/publications.md` defines what one Gold build is, which one a
  report reads, what is kept of past builds, and what reproducible promises.
- `architecture/operations.md` says how the household runs the pipeline:
  profiles, stores, input file formats, commands, and backup and restore.
- `decisions/` records accepted architectural decisions. Changes require a new
  ADR; do not silently revise a decision to fit an implementation.
- `architecture/data-maps/` holds one data map per source format and target
  layer: each target column's source and transformation. Rows marked *Map
  decision* settle what the contract leaves open; on a conflict, the layer
  contract, `decisions/` and `domains/` win.

## Explanatory Documents

`primers/` holds standalone pages that explain a decision cluster to a reader
who has to live with it. They are **not normative**: where one disagrees with
`architecture/` or `decisions/`, that document wins and the primer is stale.
Each opens by double-clicking, needs no server, keeps progress in the browser
only, and falls back to system fonts offline.

- [Overlapping exports](primers/overlapping-exports-primer.html): identity,
  the balance chain, whole-file admission, decisions, coverage, provisional.
- [Dimensional Gold](primers/dimensional-gold-primer.html): grains, the
  allocation fact, Type 1 dimensions, snapshots, balance chain, lineage.
- [Classification and transfers](primers/classification-transfers-primer.html):
  the reporting boundary, rules, transfer evidence, decisions, review items.
- [Publications and history](primers/publications-history-primer.html): the
  recipe, undo, the two time axes, retention, the decision log.
- [Operations](primers/operations-primer.html): profiles, stores, development
  from backups, inputs, the monthly import, backup and restore.

## Background Documents

Background is optional reading and owns no rule. Where it disagrees with a
document under `architecture/`, `domains/` or `decisions/`, that document wins
and the background is stale.

- `research/` holds the research notes behind decisions. The ADR that cites a
  note records what was decided.
- `agents/*-agent.md` holds one brief per layer: its mission, inputs, outputs,
  prohibited work and acceptance criteria, gathered from the layer contracts.

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
