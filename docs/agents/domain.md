---
type: agents
---
# Domain Docs

How engineering skills should consume this repository's domain documentation when exploring the codebase.

## Before exploring, read these

- **`docs/CONTEXT.md`**: the glossary.
- **`docs/decisions/`**: read ADRs that touch the area you're about to work in.

If these files don't exist, **proceed silently**. Don't flag their absence or suggest creating them upfront. The `/domain-modeling` skill creates them lazily when terms or decisions are resolved.

## File structure

This is a single-context repository:

```
/
├── docs/
│   ├── CONTEXT.md
│   └── decisions/
└── src/
```

New ADRs go in `docs/decisions/` as `ADR-NNN-slug.md`. Every new Markdown file
under `docs/` opens with the header ADR-019 sets out, and an ADR keeps its
`**Status:**` line in the body.

## Use the glossary's vocabulary

When output names a domain concept—in an issue title, refactor proposal, hypothesis, or test—use the term defined in `docs/CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If a needed concept isn't in the glossary, reconsider whether the project already has a term; otherwise note the gap for `/domain-modeling`.

## Flag ADR conflicts

Explicitly surface output that contradicts an existing ADR rather than silently overriding it.
