---
type: research
---
# Open-issue audit, 10 October 2026

## Current decision and status

The owner confirmed during this audit: **0.3 is an authenticated monthly
actuals dashboard using CSV imports. Budgets and bank connections come later.**

This audit proposes tracker changes; none has been applied to GitHub. It does
not settle the outstanding financial-policy choices listed below. Issue bodies
and comments are evidence, not authorization to implement their proposals.

Read these together:

- [Release plan and acceptance gates](release-plan-2026-10-10.md).
- [Complete 76-issue ledger](issue-audit-ledger-2026-10-10.md), including current
  native blockers and a disposition for every open issue.
- [Independent scope and architecture investigation](issue-audit-release-scope-2026-10-10.md).

## Coverage and method

The snapshot contains **76 open issues, all 15 of their comments, 46 closed
issues, 70 visible pull requests, five milestones and the repository labels**.
Both open PR descriptions were read. Closed-issue history and merged PR states
were used to check completed prerequisites; not every historical PR diff was
reviewed. GitHub's comment totals match every fetched open-issue comment list.
The dependency query includes `blockedBy`, `blocking`, parent and sub-issues;
none of those connections is truncated. The open-issue query has no next page.

The fetched main revision is
`9c16a74c1ef7264ebb2061a5fdcf94aaddf66f75`. The working checkout is an older,
detached revision, `1fb24037f9144dff9b9cc02ce6efb8b28efb6323`; it was not
switched or reset. Source findings refer to fetched main, inspected with
`git show`/`git grep`. Existing changes to the environment file and
`docs/agents/issue-tracker.md` were preserved. No private financial data was
needed. This is a tracker/contract/source audit, not a fresh runtime
reproduction of every reported bug.

The visible inventory has 18 open issues in 0.3, 42 in Later and 16 in Polish.
GitHub's milestone counters also count PRs: the extra open item in 0.3 is
[draft PR #142](https://github.com/ATherkel/budget/pull/142), not a 77th issue.
The repository-wide 78 open items are 76 issues plus two PRs.

## Main conclusion

The backlog can be split into releases now. Its main problem is not a cycle:
**the recorded dependency graph is acyclic**. It is incomplete, mixes old and
current scope, and leaves some first-application prerequisites in Later or
without an issue. Fixing those omissions is more valuable than adding a
generic `blocked` label.

Native dependencies are the repository's canonical blocking representation.
There are **58 recorded blocker edges: 40 point to open issues and 18 to closed
ones**. Eighteen open issues have at least one open native blocker. Twenty-four
issues have `ready-for-agent`; eight of those are natively blocked. That is not
necessarily contradictory: readiness can mean the specification is ready while
execution awaits a prerequisite. A work picker must require both readiness and
no open blocker, and exclude roadmap/umbrella issues and unresolved decisions.

## Dependency corrections

The direction in this table is **consumer is blocked by prerequisite**. A
completion dependency can allow fixture-based implementation to start earlier;
it means the issue cannot truthfully be completed before the prerequisite.
Do not make every related issue a dependency or add every transitive edge.

| Consumer | Missing prerequisite / change | Evidence and interpretation |
| --- | --- | --- |
| [#121](https://github.com/ATherkel/budget/issues/121) | Add **#119** | Explicitly listed in its body, absent from native dependencies. Restore requires replay/catch-up. Move #119 into 0.3 if #121 remains there. #120 is already closed. |
| [#176](https://github.com/ATherkel/budget/issues/176) | Add **#173** as a completion dependency | Its category/rule lifecycle examples and production Gold build require the completed classification chain. Present edges reach dimensions #169, but not #170 → #171 → #173. Recipe/orchestration work may start earlier against an agreed seam. |
| #176 | Add **#250 after splitting ownership as below** | The pipeline must pass the profile window and fingerprint it. #250 currently also mentions pipeline integration, so first assign its input/identity seam there and final wiring to #176; otherwise mutual waiting creates a new cycle. |
| #176 | Add **#237, #239** as production correctness gates | Both describe registry/Silver disagreement that can publish invalid facts; #237 explicitly identifies #176's stored-Silver path as the new exposure. Agree refusal policy before implementation. |
| #176 | Add **#238** as a trustworthy-publication gate | Its quiet-month case publishes stale balances as complete. It belongs before acceptance of the real pipeline, not after the first trusted dashboard. |
| [#171](https://github.com/ATherkel/budget/issues/171) | Add **#241** as the policy-location decision | Transfer matching is exactly when the postponed choice of code-pinned versus configuration-pinned policy must be settled. #176 inherits this through #173. This is not permission to add tunable transfer policy. |
| [#170](https://github.com/ATherkel/budget/issues/170) | Settle **#243** before accepting the taxonomy/classification contract | Current examples and normative taxonomy requirements disagree. This is a specification-completion gate, not permission to choose new validation rules. |
| [#179](https://github.com/ATherkel/budget/issues/179) | Settle **#252** before consumer-contract acceptance | Fix the contradictory coverage_start description while preserving the agreed managed-period grain unless the owner decides otherwise. Fixture-based report work can proceed. |
| [#175](https://github.com/ATherkel/budget/issues/175) | Coordinate shared-contract **#232** before acceptance | Both repository implementations should reject the same erroneous bare-string selection. Treat this as a small contract-first completion dependency, not a reason to halt unrelated storage implementation. |
| #176 | Settle **#244** before its no-op acceptance | Either canonicalize supported literal conditions or narrow the stated equivalence contract; do not leave two incompatible promises. |
| [#134](https://github.com/ATherkel/budget/issues/134) | Add **#178** | It says it needs Gold classification, review and decide, but its only native blocker is closed #123. #178 provides the decision boundary; Gold review also needs the owner identified below. |
| [#155](https://github.com/ATherkel/budget/issues/155) | Add **#150, #151, #192, #176** for its full stated acceptance | The stage view explicitly needs duplicate/refusal codes and Gold/publish stages; error telemetry must preserve log privacy. An initial CLI-only renderer could start earlier, but that would be a deliberate split of its current scope. |
| [#253](https://github.com/ATherkel/budget/issues/253) | Coordinate with **#238**, or record it as the green-completion blocker | Universal invariant checks will reject the known null-balance/complete result. Write failing coverage with the fix; do not disguise the defect with a permissive assertion. This relationship need not prevent starting the red test. |
| [#188](https://github.com/ATherkel/budget/issues/188) | Gold-specific acceptance follows **#175** | The generic migration runner already maps BUSY and Silver uses it. The missing work is stage-specific verification and Gold integration, not a second migration engine. Do not simultaneously block #175 on all of #188. |
| [#111](https://github.com/ATherkel/budget/issues/111) | Add **#121, #150, #177, #178**, plus the missing operational/review owners | Existing edges cover the display path, not recovery, recurring import safety, undo or the promised operator correction loop. These are proposed first-application acceptance gates, not previously agreed native links. |

The release plan supplies names and contracts for the missing owners before
any nonexistent issue numbers are used. In particular, Gold operational
integration must precede #176's production completion, and the Gold review
read surface must precede #178's complete W2 walkthrough.

The full proposed completion graph was checked with those choices, the
#253/#238 coordination represented as a green-completion edge, the two new
owners N1/N2, and the five proposed closed/consolidated issues removed. It
contains 68 open-node edges (29 additions), **no cycle and no prerequisite in
a later proposed release than its consumer**. These checks validate the plan,
not live GitHub: the existing graph remains unchanged.

### Relationships that should not be added blindly

- **#179 does not need to wait for #175 or the whole Gold pipeline.** Its
  `GoldRepository` contract and fixtures exist. Production wiring #180 has the
  store dependency; #104 already has the analytics dependency.
- **#103 can start independently of #179.** Its synthetic report adapter is an
  explicit design feature. Authentication and navigation do not need real CSVs.
- **#109 is not a prerequisite for 0.3.** Foundational publication pinning,
  superseded-page notices and unavailable-result recovery already belong to
  #103/#104/#180/#111. The history picker and historical building come later.
- **#247 is not automatically a prerequisite of #175.** Canonical snapshots
  already promise reproducibility. Exact raw-file auditing is additional scope
  with a still-open storage/no-op policy.
- **#118 is not required merely because #176 once mentioned `--from bronze`.**
  The later scope amendment narrows #176 to Gold on top of completed #199.
  Full Bronze reparsing must be explicitly delivered in its own release.
- **#114 cannot acquire a meaningful blocker until splits have a real owner.**
  Neither #112 (reserves) nor #134 (refund notes) implements mixed
  transfer-plus-fee transaction semantics.
- **#100's later children do not all block its 0.3 closure.** Its amended
  checkpoint is #111. Keep later requirements alive after that checkpoint.

### Closed and unavailable prerequisites

#113, #166, #190, #202, #203, #210, #229, #231, #236 and #242 are merged PRs.
#12, #101, #117, #120, #123, #132, #167, #168, #169, #174, #198, #199 and #200
are closed issues. Their old “do not start before merge” wording is historical,
not an open blocker. Keep historical native links if useful; a scheduler must
check state instead of counting all edges.

Eight referenced numbers are absent from the visible issue/PR inventory:
#46, #47, #48, #56, #57, #84, #85 and #87. Several are explicitly identified as
hidden originals. The recreated #114/#118/#119/#121 bodies provide current
contracts; do not pretend the unavailable history was verified. #2's remaining
hidden decision links should be replaced or supplemented with the accepted
ADR/current issue references when its map is refreshed.

## First-application gaps without adequate ownership

1. **Gold backup and migration integration.** Main still marks Gold as an
   uncovered stage and refuses a backup once it exists. The missing work is
   analogous to completed Silver backup issue #198. Without it a first display
   can appear successful while the next normal production import fails.
2. **Gold review discovery.** #199 expressly excluded Gold; `reviewing.py`
   still reads Silver only. Producing Gold review items and implementing
   `decide` does not by itself make the items discoverable to the operator.
3. **Usable authentication setup.** Assign `set-passphrase` to #103 and `serve`
   production composition to #111. These are required ends of the login flow,
   even though no separate issue is necessarily needed.
4. **Restore completion.** Resolve #121's whole-profile versus missing-store
   repair policy and all-store scope. Distinguish backup integrity checks from
   the full historical recipe verification deliberately deferred elsewhere.
5. **Minimum operating instructions.** Explicitly deliver or defer `status`
   and `check`; the operations command table currently promises more than the
   implemented CLI and issue ownership provide. The audit does not invent a
   requirement for an orchestration server or a full operational UI in 0.3.

Source anchors at the audited revision:
[backup exclusions](https://github.com/ATherkel/budget/blob/9c16a74c1ef7264ebb2061a5fdcf94aaddf66f75/src/budget/backups.py),
[stage registration](https://github.com/ATherkel/budget/blob/9c16a74c1ef7264ebb2061a5fdcf94aaddf66f75/src/budget/migration.py),
[CLI commands](https://github.com/ATherkel/budget/blob/9c16a74c1ef7264ebb2061a5fdcf94aaddf66f75/src/budget/cli.py),
[Silver review](https://github.com/ATherkel/budget/blob/9c16a74c1ef7264ebb2061a5fdcf94aaddf66f75/src/budget/reviewing.py).

## Contradictions and consolidation

| Finding | Proposed resolution |
| --- | --- |
| #145 says wait until after the dashboard; #250 requires the profile window and recipe identity in 0.3. Current main docs already adopt the profile window. | Make #250 the current owner, carry the immutable-history requirements forward, and supersede #145 explicitly. Do not carry its #111 blocker onto #250. Settle #254's minimum and whole-day validation there. |
| #255 repeats #240 item 1. | Fold into #240 and close #255 as duplicate; preserve #240's separate grouping cleanup. |
| #186 says migrate is the only command and the catch list is misleading. | Closure candidate: the current CLI comment now says the store refusals apply to every stage, and real commands that open stores exist. Its offered “keep and explain” solution is implemented. |
| #208 says the README disguises an empty-review placeholder as command output. | Closure candidate: merged #229 makes it a `#` annotation and explains that convention; the example emits it only for a successful silent review. This satisfies its second offered solution without changing CLI output. |
| #188 assumes Silver and Gold have no stores. | Partly absorbed by shared `sqlstore.migrate_store`; keep only stage-specific remaining acceptance, especially Gold. Do not close the whole issue based on Silver alone. |
| #192 assumes no import command or routine logging exists. | Logging exists, but current completion records contain counts and kinds, not raw exception messages. Treat this as a failure-logging/privacy guard before #155, not evidence of a current financial-path leak. |
| #244 calls literal-pattern case fingerprints harmless; #176 says same meaning produces no publication. | Resolve the precise equivalence promise in 0.3: canonicalize case-insensitive literal patterns or narrow the promise. Do not promise general regex equivalence. |
| #247 wants raw-file audit identity and no publication for formatting-only changes. | Decide where an attempted no-op build records its raw hashes, and whether bytes as well as hashes are retained. Hashes alone cannot recover file text. |
| #243 and #252 expose mutually inconsistent normative instructions. | Resolve the taxonomy validation and managed-period documentation before coding against them; do not silently select the most convenient document. |
| #104 still instructs financial calculations although its amendment transfers them to #179. | Rewrite the current action list: #179 computes, #104 renders and explains. Preserve the accepted all-category ordering and quiet unclassified note from the latest report contract. |
| #151 suggests editing Bronze migration 0001 before #113 merges. | That condition is obsolete: #113 merged. Any implementation now needs the repository's actual migration/compatibility policy, including historical import-log replay. |

No automatic closure is proposed for an issue merely because a related PR
merged. The closure candidates above were compared with actual source; any
remaining acceptance must be moved before a duplicate is closed.

## Readiness and decision debt

The eight natively blocked `ready-for-agent` tickets are #145, #171, #173,
#176, #177, #178, #180 and #181. The ledger records all current labels and
blockers, including blocked tickets such as #104 that lack a readiness label.

Some labels also conceal outstanding policy: #121 has a recovery decision in
comments, #102 explicitly requires budget-contract decisions, #103 requires
session-lifetime/invalidation agreement, #250/#254 need an allowed minimum,
and #100 is an umbrella. “No open blocker” does not make these autonomous
implementation tasks. #134's major owner decisions are already in comments;
do not ask them again. #159's rejected funding-link option is likewise settled.

The actual choices to carry forward are:

- #121: whole-profile recovery or coherent single-store repair; proposed default
  is preserve whole-profile restore and fix the misleading advice.
- #150: confirm that “continue” imports clean files only; the incident files
  must not become a guessed account assignment.
- #237/#239: proposed default is refuse invalid registry/Silver combinations,
  preserving the current publication, rather than silently dropping facts.
- #238: define the trailing null-balance interval; proposed default is partial
  coverage and unknown carried balances until trustworthy evidence resumes.
- #241/#243/#244/#250/#252: resolve the documented contract choices without
  growing the first release. #103 retains its security acceptance decisions.
- Later: #102 plan publication; #99 commitments; #112 reserves; #155 operational
  display form; #247 audit retention; #159 tagging authoring/history. Other
  already settled product choices remain settled.

## Release-number and source-of-truth repairs

0.1 and 0.2 milestones are closed. 0.2 means the real-data CLI, not the
dashboard. #100 and its children, #170–#181, #145's comment and the current
report contract retain old dashboard-release numbering. The roadmap still
calls pre-code Phase 0 current. Draft #142 preserves a superseded plan that
puts budgets in the first release.

Publish one current release map and concise current-scope headers on active
issues. Preserve dated decision history and human text. **Do not globally
replace `0.2`: Gold contract 0.2 and report-contract versions are schema
versions, not product release numbers.** #2 needs to become a roadmap-only map
or close as completed planning; it should not prevent shipping 0.3 because it
also indexes future work. #110/#112 should stop directing new progress to
closed #11. The modified local issue-tracker guide has stale milestone
examples too, but it was deliberately left untouched during this audit.

## Applying this audit

The release plan is a concrete proposal for review. An application pass should:

1. Re-fetch changed issue bodies/comments, preserving any newer owner decisions.
2. Settle only the outstanding release/policy choices; record current scope
   before changing dependency links that depend on it.
3. Create the two missing 0.3 delivery owners, then split/consolidate overlapping
   ownership before adding edges. Apply the release allocation from the ledger.
4. Move remaining optional maintenance to Polish; remove redundant `spare-time`
   labels from #232–#235, preserving their distinct impact and triage state.
5. Refresh active scope text/roadmap, close proven resolved or consolidated
   issues, and verify counts, acyclicity and milestone ordering again.

Every GitHub write must use `agent-gh` and the repository's attribution rules.
This audit has not posted comments, changed issues, created milestones,
committed, pushed, merged or deployed anything.

## Validation of the audit artifacts

- All 76 snapshot issues appear exactly once in the disposition ledger.
- Existing and proposed dependency graphs are acyclic; the proposed graph has
  no later-release prerequisite for an earlier-release consumer.
- All open comment counts and connection pagination were checked against GitHub.
- All relative file links in the four audit documents resolve.
- Repository documentation checks: **63 passed**. `git diff --check` passed.
  No application behavior changed, and application tests were not rerun.
