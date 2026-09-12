# Domain Docs

How engineering skills should consume this repository's domain documentation when exploring the codebase.

## Before exploring, read these

- `CONTEXT.md` at the repository root.
- Relevant ADRs in `docs/adr/`.

If these files do not exist, proceed silently. The domain-modeling skill creates them when terms or decisions are actually resolved.

## File structure

This is a single-context repository:

```
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

When naming a domain concept, use the term defined in `CONTEXT.md`. If a needed concept is missing, reconsider whether the project already has a term; otherwise note the gap for domain modeling.

## Flag ADR conflicts

Explicitly surface output that contradicts an existing ADR rather than silently overriding it.
