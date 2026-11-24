---
type: agents
---
# Pull Request Reviews

How a PR is reviewed and fixed until it is safe to merge on its own. The
rationale is in issue #362.

- **Contract**: each PR names the accepted behavior it owns, its exclusions
  and the PRs it needs first.
- **Scope**: start from the diff against the PR's base, then follow the
  callers and dependencies it touches. A finding is in scope wherever the
  code lives if this PR causes or exposes it. File unrelated pre-existing
  defects as issues.
- **Findings**: classify each one as *required* (breaks the contract or
  regresses behavior, with evidence), *decision needed* (an open scope or
  contract choice for the owner) or *optional* (stays out of the PR unless
  accepted). Do not silently downgrade a required finding or weaken its
  acceptance test. Record evidence for reclassification; disputed findings or
  changes to accepted behavior go to the owner before dependent work continues.
- **Docs**: content restated outside its owner doc is a finding. The fix is
  a link to the owner section, as
  [Writing docs](../../AGENTS.md#writing-docs) requires.
- **Fix in place**: a required finding is fixed in the PR that introduced it,
  then carried up through the branches stacked on it. A later PR never makes
  an earlier one correct; after merge, fix it in a follow-up PR.
- **Re-review**: re-check the fix, the interactions it changes and any
  conflict resolutions. Repeated design-level findings mean replanning, not
  more patches.
- **CSS declaration overlap advisory**: read the report in pytest or CI output.
  For each material overlap, require the author either to reuse/extract shared
  styles or to explain why keeping the rules separate is appropriate. One
  explanation may cover related matches. Mere overlap is not a required
  finding, and the report's mention of an earlier selector is not a reuse
  recommendation. Execution rules and the authoritative threshold are in
  [Code Quality Gate](code-quality.md#css-declaration-overlap-advisory).
- **Ready**: a PR is ready for the owner to merge once its contract holds,
  its required findings are fixed with evidence and its checks pass. Agents
  don't merge.
