# ADR-005: Use Test-Driven Development for Behavior Changes

**Status:** Accepted

## Context

Application behavior must be developed in small, verifiable increments, with
tests expressing expected behavior at public seams. A consistent workflow is
needed before implementation begins and should keep the user involved in
confirming the test boundary and reviewing each red result.

## Decision

Use red/green test-driven development for all behavior-changing application
features and bug fixes. Agree on the public test seam before writing tests,
then work one behavior slice at a time: write and run a failing test, review
the red result, and implement only enough to pass it. Refactoring belongs to a
separate review stage. Documentation-only edits, configuration-only edits, and
behavior-preserving cleanup are outside this requirement; when a meaningful
red test is infeasible for behavior-changing work, record the reason and
alternative verification.

## Consequences

- Tests specify observable behavior and guard each change before implementation.
- Implementation proceeds in small vertical slices rather than horizontal
  batches of tests and code.
- Red/green work has explicit user review points, with review and refactoring
  kept separate from the implementation loop.
- An exception requires an explanation and alternative verification.
