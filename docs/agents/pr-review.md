---
type: agents
---
# Pull Request Reviews

How a PR moves from review to merge, so a stack of PRs never needs rework
below its top.

- **Scope**: a critical review covers only the PR's own diff, taken from the
  merge-base with the PR's base branch. File each finding outside that diff
  as an issue instead of fixing it in the PR.
- **One round**: each PR gets one review round. Once its findings are fixed
  or filed, the PR is frozen: no further commits.
- **Fix forward**: after review, the stack only grows upward. A problem found
  later in a frozen PR is fixed in a new PR on top of the stack, not by
  rewriting the PR that holds it.
- **Merge on pass**: merge each PR as soon as it passes review and CI. Don't
  hold it for the PRs above it.
