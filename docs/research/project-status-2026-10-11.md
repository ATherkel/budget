---
type: research
---
# Budget project status, 11 October 2026

## Where the project stands

Budget has a released command-line foundation and is building its first usable
application. The next finish line is **0.3: authenticated monthly actuals from
CSV imports**, including correction, repeat operation and safe recovery.
Budgets and bank connections are later releases. The remaining work is more
than rendering a dashboard: trustworthy classification, publication, analytics
and operating integration must meet in one household workflow.

[v0.1.0](https://github.com/ATherkel/budget/releases/tag/v0.1.0) was published on
6 October and [v0.2.0](https://github.com/ATherkel/budget/releases/tag/v0.2.0) on
8 October 2026. Both are marked prereleases. The 0.2 release is real data through
the CLI; its release tag is no longer an outstanding task.

The audit found a coherent direction obscured by incomplete dependencies,
superseded instructions, missing integration owners and undecided policy. These
are distinct from implementation progress. Resolving or labelling a question
does not mean its feature has shipped; adding a milestone does not establish a
delivery date.

## Evidence and current tracker

The [audit](issue-audit-2026-10-10.md), [76-issue ledger](issue-audit-ledger-2026-10-10.md)
and [release plan](release-plan-2026-10-10.md) preserve the pre-update snapshot
and reasoning. The [application report](issue-audit-application-2026-10-11.md) records the subsequent GitHub changes,
new issue numbers, verified counts and remaining decisions. Use that report and
live GitHub for current assignments rather than interpreting the old ledger as
a second tracker.

The approved tracker update is applied: **75 open issues**, including 32 in
0.3, 9 in 0.4, 3 in 0.5, 3 in 0.6, 5 in 0.7 and 3 in 0.8. Later has two,
Polish has 17 and #2 remains the milestone-free roadmap. Five issues were
resolved/consolidated and four owners created: #257 Gold operations, #258 Gold
review discovery, #259 history scoping and #260 connector scoping. Twenty-five
issues are explicitly `ready-for-human`; the application report groups them by
urgency. The verified graph has 71 open-issue edges and no cycles or dependencies
from an earlier numbered release onto a later one.

Source inspection in the audit used main at
`9c16a74c1ef7264ebb2061a5fdcf94aaddf66f75`, rather than the older detached working
checkout. This is a planning/status assessment, not a new end-to-end household
trial. Closed issues are evidence of accepted delivery scope, not a claim that
every surrounding feature is complete.

## What exists and what remains

| Area | Evidence-backed position | Remaining delivery |
| --- | --- | --- |
| CSV and stores | Bronze/Silver storage, migrations, import, Silver rebuild/review and supported backup operations are in the released foundation. | Recovery, correctness follow-ups and Gold operating integration. |
| Gold foundations | #167 contract types, #168 taxonomy/rules inputs and #169 core Gold results are closed. | #170/#171/#173 classification and transfers; #172 decision log; policy corrections. |
| Published reports | Report contract #101 and shared migration foundation #174 are closed. | #175 persistence, #176 pipeline, #177 diff/undo, #179 analytics and #180 publication readers. |
| Operator corrections | Silver review is available. | Gold review discovery and #178 decisions must form a usable correction loop. |
| Dashboard | Contracts and prototype references exist. | #103 authentication/shell, #104 overview and #111 production composition and household acceptance. |
| Later capabilities | Requirements and some specifications exist. | Budgets, history, commitments and connectors need delivery work; some still need scoped prerequisites. |

The important operational gap is that Gold storage alone does not make Gold
safe to operate: migration registration, backup sets and the next normal import
must all support it. The important correction gap is that producing a review
item does not make it discoverable or actionable.

## Release finish lines

| Release | Household outcome |
| --- | --- |
| 0.3 | Read trustworthy monthly actuals after importing CSVs; correct an ambiguous item; repeat and recover the workflow. |
| 0.4 | Investigate category/account figures and understand operational failures. |
| 0.5 | Compare actuals with household budgets and inspect trends. |
| 0.6 | Browse and reproduce supported historical results with honest retention and availability behavior. |
| 0.7 | Handle commitments, trips and refund notes; resolve reserve policy without implying reserve implementation is already scoped. |
| 0.8 | Connect a consented read-only bank source, with access lifecycle and recovery behavior. |
| Later | Deliberately uncommitted splits/fee-transfer and packaging scope. |
| Polish | Optional low-impact maintenance; no release gate without new evidence of material impact. |

These are outcomes, not effort estimates. History and bank connections contain
substantial missing delivery scope; their small issue counts must not imply
they are nearly complete. The detailed gates remain in the release plan.

## What the owner should do next

Work through the first-release decision queue in small groups:

1. **Trust in the figures:** #237/#239 invalid account/registry combinations,
   #238 missing trailing balances, #243 taxonomy requirements and #252 coverage
   wording. These determine what can truthfully be shown as complete.
2. **Repeatable identity:** #241 transfer policy identity, #244 no-op meaning
   and #250 allowed late-booking window. Record precise bounded rules; do not
   promise arbitrary regex equivalence.
3. **Safe normal use:** #121 recovery destination/coherence, #150 clean-file
   continuation and #103 authentication/session decisions. #111 also needs an
   honest boundary for minimum operating commands and instructions.

An issue requiring one of these choices should be `ready-for-human`, with the
question stated on the issue. A suggested default is still a suggestion until
the owner answers. Already answered #134 decisions and #159's rejected option
should not be asked again. Later-release questions can wait unless they change
an immediate shared contract.

After an answer, update the current contract and acceptance criteria, retain a
link to the decision, and only then change the issue to `ready-for-agent` if it
is fully specified. Native dependencies remain separate from readiness.

## How implementation should flow

Use the verified GitHub graph to choose a small number of fully specified,
unassigned tasks with no open blockers. The potential independent seams are
decision-log parsing, Gold storage, analytics from fixtures, the synthetic
dashboard shell after its security choices, and archive replay. Their actual
startability depends on their current contracts and blockers; this list is not
a blanket dispatch instruction.

Classification and decisions feed the complete pipeline. Gold storage feeds
operating integration and publication readers. Gold review discovery feeds
the correction walkthrough. Dashboard rendering consumes analytics; it does
not calculate its own financial answers. Final #111 acceptance brings these
tracks together with repeat import, correction, undo, recovery and the household
trial. Fixture success is useful intermediate evidence, not the release gate.

Do not present a longest dependency chain as a calendar forecast. Native links
may represent completion gates even when fixture implementation can begin
earlier. The route map should explain that distinction.

## Updating the Claude artifact

The owner values [Budget Next Steps](https://claude.ai/artifact/J1ZUYSZ1LMgSQM55D6P8DM).
Its visible content was read in the browser on 11 October; it says updated
8 October. Preserve its walk/PC/everything filters, DECIDE/BUILD/MERGE/TIDY/PC
categories, in-progress notes, hide-done control, release sections, useful
issue links and dependency waves. Update the information behind those controls.

Specific changes needed:

- Mark the 0.2 release tag complete and retire the stale #219 merge prompt after
  confirming its live state. Remove the claim that Gold has not started: the
  foundational #167/#168/#169 are already closed.
- Replace the broad post-0.3 Later section with 0.4–0.8, a small Later queue
  and optional Polish. Show new integration owners and history/connector scope.
- Replace the obsolete #145 parking step with the current #250 decision.
  Use the application report for all consolidations and closures.
- Put first-release owner decisions in a prominent “decide next” queue with
  the question, affected work and issue link. Do not mix them with optional tidy
  tasks or claim every old needs-triage item is harmless to 0.3.
- Rebuild dependency waves from the updated native graph. Restore #121 is not
  immediately runnable just because the older artifact omitted its blockers.
- Separate GitHub state, prerequisite state, decision readiness and personal
  local progress. Local checkboxes must not silently override a fresh GitHub
  snapshot. Preserve notes and stable IDs where meanings are unchanged;
  migrate or retire superseded IDs explicitly.
- Recompute totals and defaults. A milestone's API counter can include PRs;
  issue counts, action-card counts and completion percentages are different.
  Do not derive effort percentages from issue counts.
- Keep #2 as a cross-release roadmap; #100's first-dashboard acceptance is
  bounded by #111 rather than all its later-release children.
- Keep household trial and owner review/release actions visible. Do not mark
  them complete based solely on implementation or an agent's review.
- Historical session, branch-cleanup, appeal and other-repository cards were
  outside this audit. Preserve them as unverified carry-forwards or refresh
  their evidence; do not guess their state or delete them as if audited.

The artifact should show its data-as-of date, distinguish verified state from
personal notes and link back to GitHub. Public rendering was readable; editing
rights and a route to update the existing artifact were not established here.
Claude should inspect its available capabilities and, if direct editing is
unavailable, produce a complete replacement artifact/source and clear owner
instructions rather than claim the hosted artifact was updated.

## What “done” will mean

1.0 should mean the household can rely on agreed workflows, maintain the
installation and recover data without routine agent intervention. Decide its
final must-have list after using 0.3 and budgets. A zero-length issue list is
not the finish line; forecasts, broader planning and optional polish need not
all precede a reliable release.
