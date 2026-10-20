---
type: research
---
# Issue audit application, 11 October 2026

## Result

The owner approved the release plan and issue ledger and requested explicit
`ready-for-human` labels for decision debt. The tracker update is now applied
and read back from GitHub. Financial-policy choices remain unanswered; their
owning issues state the questions rather than silently accepting audit defaults.

There are **75 open issues**: the original 76, minus five resolved/consolidated
issues, plus four new owners. All original open issues have the approved
disposition. Milestone counts below exclude pull requests.

| Milestone | Open issues |
| --- | ---: |
| 0.3 First dashboard | 32 |
| 0.4 Spending investigation and operations | 9 |
| 0.5 Budgets and trends | 3 |
| 0.6 History and reproducibility | 3 |
| 0.7 Commitments, trips and refund notes | 5 |
| 0.8 Bank connections | 3 |
| Later | 2 |
| Polish | 17 |
| Roadmap #2, no milestone | 1 |

0.4–0.8 now exist with outcome/gate descriptions and no due dates. 0.3 states
actuals-only scope, analytics over Gold, repeat operation, recovery and household
acceptance. Later holds #114 and #209. #100 remains the 0.3 umbrella; its
`ready-for-agent` label was removed because it is not an autonomous build ticket.

## New ownership

| Issue | Purpose | State of specification |
| --- | --- | --- |
| [#257](https://github.com/ATherkel/budget/issues/257) | Gold migrations, complete backup sets and repeat production operation | Bounded delivery scope; depends on #175/#188. |
| [#258](https://github.com/ATherkel/budget/issues/258) | Discover Gold review items and decision targets | Bounded delivery scope; depends on #173/#175 and blocks #178. |
| [#259](https://github.com/ATherkel/budget/issues/259) | Scope history discovery, replay, retention and legacy handling | Requires human specification and later bounded delivery tickets; blocks #109. |
| [#260](https://github.com/ATherkel/budget/issues/260) | Scope and deliver a consented read-only bank source | Requires human specification and bounded delivery tickets; #182/#248 are completion prerequisites. |

The latter two are deliberate scoping initiatives, not claims that history or
bank access is ready to implement. No provider, credential design, retention
policy or public deployment was selected by this update.

## Contradictions and consolidation applied

- #145 and #254 closed into #250, retaining immutable historical window
  identity and whole-day validation at the public build seam. The allowed
  minimum remains a human decision. #250 owns the input/identity seam; #176
  owns final wiring, avoiding a circular dependency.
- #255 closed into #240, retaining its non-empty-history precondition/interface
  acceptance and #240's separate grouping cleanup.
- #186 and #208 closed as resolved against the audited main implementation:
  the all-stage CLI explanation and the explicitly annotated walkthrough
  satisfy their offered solutions. Their closure comments explain this.
- #188 retains remaining stage-specific acceptance; #192 remains a privacy
  guard without claiming an observed current leak; #151 supersedes the obsolete
  suggestion to edit migration 0001 before #113 merged.
- #104 explicitly renders #179's analytics. #103 owns usable passphrase
  provisioning. #111 owns production serving, operating instructions and
  the complete household workflow. #121's current scope covers coherent
  supported-store recovery while keeping its destination/repair policy open.
- #2 now provides the current release map. Dated historical instructions and
  Gold schema-version numbers were preserved, with current-scope amendments
  taking precedence for execution.
- Removed redundant `spare-time` from #232–#235; #232 is in 0.3 and #233–#235
  are in Polish.

## Human decision queue

**25 open issues carry `ready-for-human`**, with no simultaneous
`ready-for-agent` label. The label description and repository mapping now
include owner decisions and specification as well as human implementation.

| Timing | Issues | Questions to resolve |
| --- | --- | --- |
| 0.3: financial trust | #237, #238, #239, #243, #252 | Registry disagreements, trailing missing balances, taxonomy obligations and managed-period wording. |
| 0.3: reproducibility | #241, #244, #250 | Transfer policy identity, bounded no-op equivalence and valid late-booking minimum. |
| 0.3: operation/access | #103, #111, #121, #150 | Session lifetime/invalidation, minimum command scope, recovery coherence and clean-file continuation. |
| 0.4 | #155 | Operational display surface and minimum fields. |
| 0.5 | #102 | Remaining budget validation/history details within accepted household TOML scope. |
| 0.6 | #109, #247, #259 | Historical delivery decomposition, raw input retention and no-op provenance. |
| 0.7 | #99, #112, #159 | Commitments, reserves and remaining trip authoring/history semantics. |
| 0.8 | #182, #248, #260 | Source/account contract, operative setup documents and connector scope. |
| Later | #114, #209 | Split/fee semantics and supported packaging model. |

Use the [live decision queue](https://github.com/ATherkel/budget/issues?q=is%3Aissue%20is%3Aopen%20label%3Aready-for-human).
Existing accepted household-budget scope, #134 decisions and #159's rejected
funding-link option were not reopened. An erroneous intermediate audit comment
on #102 offered per-account authoring again; the prominent current clarification
explicitly corrects that and preserves the accepted household-first contract.

`ready-for-agent` means fully specified, not necessarily unblocked. Select
actual work using open native prerequisites as well as labels and assignment.
Some links express completion gates while fixture work can begin earlier.

## Verification and execution record

- Fresh issue bodies, comments, labels, milestones and native blockers were
  retrieved after the final corrections.
- Checked all original ledger assignments plus the four new issues, all five
  closures, roadmap placement and redundant-label removal.
- The live graph contains **89 edges**, of which **71 connect open issues**.
  It is acyclic, contains every required audit dependency and has no numbered
  release blocked by a later numbered release. No open consumer still names
  one of the five closed duplicates/resolutions as a native blocker.
- Issue and blocked-by GraphQL connections report no further pages.
- Final repository documentation validation: **65 passed**;
  `git diff --check` passed. Application tests were not rerun for tracker/docs work.
- The dependency graph includes the missing #121/#119, classification and
  correctness gates for #176, N1/N2 edges and #109/#259 scope prerequisite.
- Root review corrected incomplete decision labels, a #233 milestone mismatch,
  missing native edges and ambiguous current-scope wording from the initial
  Flash pass. Final acceptance is based on read-back verification, not the
  worker's progress statements.
- The configured worker role was Flash 4.1 through the pinned DeepSeek API
  route. Static routing checks passed; independent provider request metadata
  was not available, so runtime routing is not independently certified here.

Raw snapshots, correction payloads and `verify-final.py` are preserved outside
the repository in the session's `issue-audit-evidence` artifact directory.
The final files are `verified-issues.json`, `verified-graph.json`,
`verified-milestones.json` and `verified-summary.json`; older `after-*` files
are intermediate and must not be mistaken for accepted final state.

No application behavior changed. No commits, pushes, merges, approvals or
deployments were performed. The pre-existing environment and issue-tracker
edits were preserved. The earlier audit/ledger/release-plan files remain dated
research snapshots; this report and live GitHub supply the applied state.

## Next step

Start with the 0.3 human decisions grouped above, then dispatch a small number
of fully specified tasks from the unblocked frontier. The
[project-status document](project-status-2026-10-11.md) supplies the household
narrative and the concrete update brief for the Claude artifact. The artifact's
historical other-repository/session/branch-cleanup cards still require their own
evidence and were not actioned by this audit.

The requested `claude-handoff` was launched successfully as background session
`62ac5e8e`, **Refresh Budget Next Steps artifact**, referencing these documents.
Manage it with `claude agents` or `claude attach 62ac5e8e`. Launch confirmation
does not mean the hosted artifact has already been updated; the Claude task
must verify editing capability or supply a replacement and owner-only steps.
