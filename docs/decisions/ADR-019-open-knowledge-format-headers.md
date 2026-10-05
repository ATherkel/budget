---
type: decisions
---
# ADR-019: Open Knowledge Format Headers for the Docs

**Status:** Accepted

## Context

`docs/` already keeps one file per concept, sorted into folders by kind and
linked to each other. A tool reading the folder, such as a graph viewer, a
search index or an agent, can tell an ADR from a domain document only by its
path.

The [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format)
(OKF) v0.2 is a vendor-neutral convention for exactly this layout: a folder of
Markdown files, each opening with a YAML header. Its only requirement is that
every Markdown file other than `index.md` and `log.md` has a header with a
non-empty `type`. Every other field is optional, and a reader must not reject a
file for leaving one out.

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
translate a type back to a folder, and a new folder defines a new type.

`tests/test_docs_frontmatter.py` checks every file against this rule, and the
`pytest` workflow runs it like any other test.

## Considered Options

- **Descriptive type names** (`Decision Record`, `Layer Contract`,
  `Agent Brief`). Each is a name the reader has to translate back to the
  folder it means, and `Agent Brief` is wrong for `agents/tdd.md` and
  `agents/code-quality.md`. Rejected.
- **The repository root as the bundle, keeping `CONTEXT.md` where it was.**
  `README.md`, `AGENTS.md` and `CLAUDE.md` would then need headers too.
  Rejected.
- **OKF's optional fields.** Each would be a second place to keep true:
  - `status` allows only `draft`, `stable` or `deprecated`, while an ADR's
    `**Status:**` line also records what amends or supersedes it.
  - `generated` names the agent that wrote a file, inside the file. Agent
    attribution belongs in commit metadata and GitHub text, not in the
    repository.
  - `verified` needs a date updated on every review.
  - `title` and `description` repeat the heading and the opening paragraph.
  - `index.md` and `log.md` are hand-kept lists. `README.md` already maps the
    docs, and `git log` records their changes.
- **OKF's reference agent as a dependency.** It builds bundles from BigQuery
  and calls Gemini; neither applies here. Its `visualize` command runs from a
  separate checkout against `docs/`. Rejected.
- **Parsing the header with PyYAML.** It would be the first dependency added
  only to read a one-key header. The test instead requires the exact
  three-line form, which is valid YAML. Revisit if a second key is adopted.

## Consequences

- The header moves every line in `docs/` down by three. This change shifts the
  line citations in `research/`, but citations elsewhere, in GitHub issue
  bodies and in `prototypes/import-identity/`, now point three lines early.
- A new document fails the test until it has its header, and a document moved
  to another folder must change its `type`.
- `agents/domain.md` gives the glossary's new path; skills that look for
  `CONTEXT.md` find it there.
- To see the bundle as a graph, run OKF's viewer from its own checkout:
  `python -m reference_agent visualize --bundle <budget>/docs --out docs.html`.
