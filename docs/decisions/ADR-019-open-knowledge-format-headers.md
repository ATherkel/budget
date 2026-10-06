---
type: decisions
---
# ADR-019: Open Knowledge Format Headers for the Docs

**Status:** Accepted

## Context

`docs/` already keeps one file per concept, sorted into folders by kind and
linked to each other. A tool reading the folder, such as a graph viewer, a
search index or an agent, has no field that says what kind of document each
file is, so it cannot group or filter them.

The [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format)
(OKF) v0.2 is a vendor-neutral convention for exactly this layout: a folder of
Markdown files, each opening with a YAML header. It reserves two names:
`index.md` for a directory listing and `log.md` for a change history. Its one
requirement on every other Markdown file is a header with a non-empty `type`,
which readers use to group and filter documents. Every other field is
recommended or optional, and a reader must not reject a file for leaving one
out.

The household's main risk to the project is upkeep, so every field adopted is
one more thing to keep true.

## Decision

`docs/` is an OKF v0.2 bundle, and `CONTEXT.md` moves into it so the glossary
is part of the bundle.

Every Markdown file under `docs/` opens with a header holding one key, `type`:

```yaml
---
type: decisions
---
```

`type` is the name of the folder the file sits in, copied exactly:
`architecture`, `decisions`, `domains`, `agents`, `developers`, `research` and
`data-maps`. A file directly in `docs/` has no folder to copy, so
`CONTEXT.md` is `glossary` and the others are `overview`. A reader never has to
translate a type back to a folder, and a new folder defines a new type. OKF
asks that types be descriptive; the folder names are, to anyone who knows the
layout.

`tests/test_docs_frontmatter.py` checks every file against this rule, and the
`pytest` workflow runs it like any other test. It also refuses a file named
`index.md` or `log.md`, the names OKF reserves for the files this ADR does not
adopt.

## Considered Options

- **Descriptive type names** (`Decision Record`, `Layer Contract`,
  `Agent Brief`). Each is a name the reader has to translate back to the
  folder it means, and `Agent Brief` is wrong for `agents/tdd.md` and
  `agents/code-quality.md`. Rejected.
- **The repository root as the bundle, keeping `CONTEXT.md` where it was.**
  `README.md`, `AGENTS.md`, `CLAUDE.md` and every other Markdown file in the
  repository would then need headers too.
  Rejected.
- **OKF's other fields.** Each would be a second place to keep true. Rejected:
  - `title` and `description`, which OKF recommends, repeat the heading and
    the opening paragraph.
  - `resource` and `tags`, also recommended: no document describes an asset
    with its own URI, and tags, which group documents across folders, would be
    one more list to keep true while nothing here reads them.
  - `status` allows only `draft`, `stable` or `deprecated`, while an ADR's
    `**Status:**` line also records what amends or supersedes it.
  - `generated` records who wrote a file, inside the file. For an agent that
    is attribution, which belongs in commit metadata and GitHub text, not in
    the repository.
  - `verified` needs a date updated on every review.
- **OKF's `index.md` and `log.md` files.** `README.md` already maps the docs,
  and `git log` records their changes. Rejected.
- **OKF's reference agent as a dependency.** It builds bundles from BigQuery
  and calls Gemini; neither applies here. Its `visualize` command runs from a
  separate checkout against `docs/`. Rejected.
- **Parsing the header with PyYAML.** It would be the first dependency added
  only to read a one-key header. The test instead requires the exact
  three-line form, which is valid YAML. Rejected; revisit if a second key is
  adopted.

## Consequences

- The header moves every line in `docs/` down by three. The line citations in
  `research/` were updated and then replaced by section links, as
  [`docs/README.md`, *Conventions*](../README.md#conventions) now asks, and the open issues that cited docs by
  line now link to lines at a fixed commit instead. The citations in
  `prototypes/import-identity/` were not updated and are now three lines
  further off.
- A new document fails the test until it has its header, and a document moved
  to another folder must change its `type`.
- Skills expect `CONTEXT.md` at the repository root. `AGENTS.md` and
  `agents/domain.md` name `docs/CONTEXT.md` instead.
- To see the bundle as a graph, run OKF's viewer from its own checkout:
  `python -m reference_agent visualize --bundle <budget>/docs --out docs.html`.
