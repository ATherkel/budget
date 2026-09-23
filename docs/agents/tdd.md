# Test-Driven Development Workflow

Use this workflow for every application feature and bug fix that changes
behavior. Work in small red/green slices, with an explicit handoff between the
test-writing and implementation phases. Refactoring happens in a separate
review stage after the behavior is green.

## Before the first test

- Read the relevant domain documents and accepted ADRs.
- Describe the public behavior and agree with the user on the public seam where
  it will be observed. Do not write a test until the seam is agreed.
- Identify the smallest behavior slice to implement. Do not write a batch of
  tests for imagined future behavior.
- If a later slice needs a different public seam, agree on that seam before
  writing its test.

## Red phase

- Write one focused test for the agreed behavior through the public seam.
- The test must describe observable behavior, not private methods, internal
  call sequences, or implementation structure.
- Run the test before implementation. Show the test and its failure to the
  user, and wait for review before handing off to the green phase.
- Confirm that it fails because the behavior is missing or incorrect. A test
  that fails because of a syntax error, broken setup, or unrelated failure is
  not a valid red result.

## Green phase

- Implement only enough application code to make the reviewed red test pass.
- Do not change or weaken the test to make the implementation pass. If the test
  or expected behavior is wrong or unclear, return to the user and red phase to
  resolve it.
- Run the focused test and report the command and result. Then repeat with the
  next smallest behavior slice.

## Review and refactoring

After the behavior slices are complete, review the change and refactor in a
separate stage. Refactoring must preserve behavior; keep the tests passing and
do not add behavior without first returning to a red test. Run the relevant
test suite and the [code quality gate](code-quality.md) after refactoring.

Tests should assert known behavior through public interfaces and use
independent expected values. Avoid tests that mirror implementation, assert
private details, or mock project-owned collaborators. Mock only system
boundaries when needed.

## Exceptions

Documentation-only edits, configuration-only edits, and behavior-preserving
cleanup do not require a red test. For behavior-changing work where a
meaningful failing test is genuinely infeasible, state why and record the
alternative verification used in the change summary. Do not use this exception
merely because writing the test is inconvenient.

## Handoffs

Keep red and green as separate roles even when one agent coordinates the work.
The red role reports the test and its expected failure, then stops for user
review. The green role starts only after that review. The coordinator preserves
this sequence for every slice and runs a separate review/refactor stage after
the behavior is complete.
