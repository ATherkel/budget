# Dashboard #11 round-two checkpoint

## Artifact publication — 29 September 2026

The maintainer authorized committing the prototype/specification artifacts,
pushing codex/prototype-11-round-2 and opening a draft PR. He separately approved
the exact INP001/CPY001 exceptions for the three standalone prototype scripts;
pyproject.toml now applies them without changing other rules or thresholds.

The production specification is #100, with first-release tasks #101–#109 and
#111, and follow-ups #110/#112. The full plan is under docs/plans. Confirmed
choices include household TOML budgets, immutable Publication plan history,
future account-specific budgets, group/Category trend selection and the defaults
recorded in the spec. Fixed expenses/rådighedsbeløb and reserves follow release
one. Production implementation remains gated by contract work and #12.

Fresh publication checks: 2,272 fixture assertions and JavaScript syntax pass;
formatting, types and complexity pass. The lint exceptions resolve the six known
findings; publication runs the complete quality gate again after applying them.
Earlier browser evidence remains valid because application code is unchanged.
Household review is still outstanding. The pre-existing .codex directory is
excluded from the publication; no workflow or private bank files are included.

The draft PR and final commit IDs are recorded in GitHub and this task's final
message, so this pre-commit document does not claim a future push has succeeded.
Earlier checkpoint sections below are historical and may describe resolved
questions as pending.

🤖 Added by Codex (GPT-6 Astra)

## Latest checkpoint — 28 September 2026

Third prototype pass is functionally accepted by Astra after one correction.
Flash implementation: `/root/dashboard_trends`, now completed and interrupted.
See TRENDS-PLAN.md and TRENDS-IMPLEMENTATION.md. Baseline for this pass is
`%TEMP%/budget-dashboard-11-before-trends-20260928/dashboard-11`.

Enkel now has Mod budget and elapsed-month markers, without reserve/savings
reconciliation. Advanced trends have Budgetteret and category selection. Monthly
expense budgets exclude the holiday reserve. Unavailable budgets stay unknown.
Actual category gaps and refunds are preserved. Astra requested restored
unclassified-amount wording and qualified zero labels; Flash implemented both.

Worker checks: 2,272 fixture assertions, negative control, JS syntax, Python
format/types/complexity pass. Six pre-existing Ruff findings remain; the owner
has NOT approved exceptions. No other quality gate is claimed clean by omission.
Astra reviewed the actual changed code and documentation against the snapshot.

Astra CUA verification: Enkel budget/marker/no savings panel, furniture actual
8,700/1,900 against 1,500 monthly budget, missing April vs zero May–July, negative
600 clothing refund, single-account budget unavailable, visible category reset,
historical-publication budget isolation/banner, custom and invalid ranges, YTD
recovery. Corrected zero labels include coverage/provisional state and state
only that no categorized expense is present. Desktop 1280 and phone 390/320
viewports have no document overflow; screenshots inspected, console errors/warns
empty. Temporary viewport restored. Preview at http://127.0.0.1:8011/ remains open.

User approved read-only budget comparison for first production release, targets
maintained outside dashboard; editing and forecasting deferred. Recorded on #2:
https://github.com/ATherkel/budget/issues/2#issuecomment-5865909851

User also approved planned monthly rådighedsbeløb (planned take-home income minus
planned fixed expenses), but challenged per-category classification and requested
a separate design issue. Created #99 with the open per-transaction versus plan
modeling question, linked directly to the originating #11 finding:
https://github.com/ATherkel/budget/issues/99
https://github.com/ATherkel/budget/issues/11#issuecomment-5865951679
No fixed/other classification or rådighedsbeløb number was implemented in this
prototype; this is deliberately the unresolved production contract in #99.

GitHub auth now works using escalated agent-gh. WIP timeline posted:
https://github.com/ATherkel/budget/issues/11#issuecomment-5865881399
Earlier queued comments are superseded by the consolidated current updates;
do not post them as though they describe today's state.

Recommendation: use this iteration as the UI/behavior reference, resolve #99 and
the production budget/report contracts, then build production vertical slices
using normal TDD. This is a recommendation, not authorization to start production
or close #11. Household trial of this iteration still outstanding.
No commit/push; prototype remains untracked. Preserve .codex pre-existing files.
Routing doctor static-ready for DeepSeek V4.1 Flash; actual root session metadata
confirmed gpt-6-astra despite global Terra default. Provider inference metadata
remains unverified.

---

27 September 2026 — implementation and one correction cycle reviewed.
Functionally ready for a user trial; quality gate decision pending.

- Root workspace: `C:/Users/Therkel/.codex/worktrees/641b/budget`.
- Branch: `codex/prototype-11-round-2`; base `59f732f2db3a5a03b1b6dcd3bd43427842457c65`.
- Source prototype/handoff: `df907f2381e2581b4a496b2535b060be90dedcbc`.
- Completed worker: `/root/dashboard_round_2`, native `astra_flash_builder`;
  interrupted after completion so the host marks it done.
- Worker owns prototype directory except this checkpoint and ROUND-2-PLAN.md.
- `.codex/environments/` predates this task; leave it untouched.
- Accepted user choices and full brief: [ROUND-2-PLAN.md](ROUND-2-PLAN.md).
- [Round-two WIP posted to #11](https://github.com/ATherkel/budget/issues/11#issuecomment-5848770964).
- User explicitly asked to keep #11's progress-comment timeline going. GitHub
  comments must be English and carry attribution. Use `agent-gh` for every gh
  command, including reads. No publication/commit performed on this branch.

Initial report: ROUND-2-IMPLEMENTATION.md. Astra found diagnostics leaking into
Simple/Advanced overview, broken year-to-date and budget-demo navigation, no-data
counts shown as known zeros, missing export range starts in provisional fixtures,
unpinned quality-tool versions and several DTO omissions. One consolidated
correction resolved these functional findings. Astra re-read affected code and
the fixture rules, inspected the browser measurements and the desktop screenshot.
Fixture audit: 2,236 checks pass; JS syntax, Python format/types/complexity pass.
The locked Ruff still reports INP001 and CPY001 for the three scripts. Exact
prototype-only exceptions are in LINT-PROPOSAL.md, not applied without approval.
The prototype server is at `http://127.0.0.1:8011` (worker-started PID 40544).

Pending user replies:
1. Refresh the missing agent GitHub credential locally via Set-AgentToken, or
   keep comments queued. The attempted review comment did not post; the initial
   WIP comment linked above did post. Do not paste/read secret values into chat.
2. Approve the exact three-file lint exceptions, or leave the lint findings.
   This approval is explicitly required by docs/agents/code-quality.md.

Resume: if lint exceptions are approved, apply only the proposed entries to
pyproject.toml and rerun locked Ruff for the changed configuration; no broad test
rerun is needed. If the credential is refreshed, post queued review/completion
comments through agent-gh with attribution. Otherwise report that they are local.
The browser open request was queued in Codex. Let both participants try the three
tasks in README, then record actual observations. Keep #11 open. No commit or
push has been performed, and no production or workflow files were changed.

Routing is statically verified for DeepSeek V4.1 Flash through DeepSeek API;
end-to-end provider inference metadata has not yet been verified.

27 September follow-up: the maintainer requested an elapsed-month marker and
accepted uncertainty from uneven spending/late postings. Added in app.js/style.css
on monthly Mod budget bars, using the explicitly fixed fixture date (15/30 =
50%); excluded carry-forward reserves and closed months. Eight calendar cases
and live browser verification pass: seven September markers at 50%, no Ferie
marker, no markers in August. SESSION.md records the request. Whether to expose
Mod budget in Simple was asked and remains unanswered. ISSUE-11-TIME-MARKER.md
is another queued comment: posting again failed because AGENT_TOKEN is missing.
