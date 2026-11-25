---
type: agents
---
# Presentation Agent Brief

## Mission

Build a responsive, accessible dashboard from analytics report DTOs.

## Inputs

- Analytics service/API contract and documented presentation requirements.
- Synthetic report fixtures.

## Prohibited Work

- Querying Gold directly or importing any upstream-layer module.
- Performing report arithmetic or mutating financial facts.
- Displaying raw account identifiers, credentials, or source payloads.

## Structure Rules

- One feature per folder: `src/budget/dashboard/features/<name>/`.
- Wiring a feature into a shared place (router, navigation, base layout) takes
  one to three lines.
- Reuse existing CSS before adding any.
- Templates hold no logic; compute values before rendering.
- One concern per PR. Split by concern, not by line count.

The checks that enforce these are linked from
[Code Quality Gate](code-quality.md).

## Acceptance Criteria

- Core views work at phone widths.
- A changed bank connector leaves UI code untouched.
- Empty and partial periods are handled intentionally rather than presented as
  misleading zeroes.
