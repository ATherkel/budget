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

## Acceptance Criteria

- Core views work at phone widths.
- A changed bank connector leaves UI code untouched.
- Empty and partial periods are handled intentionally rather than presented as
  misleading zeroes.
