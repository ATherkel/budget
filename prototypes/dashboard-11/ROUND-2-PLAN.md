# Dashboard #11: second prototype round

Coordinator: Codex (GPT-6 Astra). Implementation: one native Flash worker.
Date: 26 September 2026; reviewed 27 September. Status: implemented and ready
for a user trial; final quality acceptance awaits the explicit lint decision
in LINT-PROPOSAL.md. No participant has validated this iteration yet.

## Baseline and purpose

- Worktree: `C:/Users/Therkel/.codex/worktrees/641b/budget`.
- Branch: `codex/prototype-11-round-2`, based on current `origin/main`
  `59f732f2db3a5a03b1b6dcd3bd43427842457c65` (154 commits beyond the old base).
- Prototype files copied, without merging old repository infrastructure, from
  `claude/modest-galileo-9daepj` at `df907f2381e2581b4a496b2535b060be90dedcbc`.
- Initial tracked/staged diff was empty. Pre-existing untracked
  `.codex/environments/` belongs to the user and must remain untouched.
- Original prototype branches remain intact. Source comparison baseline is the
  `prototypes/dashboard-11/` directory in that source commit, also archived in
  `%TEMP%/budget-dashboard-11-df907f2-baseline` for review.

Question: can an everyday reader understand the month without doing account
maintenance, while a curious reader can inspect the same figures and evidence?
Keep the familiar Danish UI and one design. The earlier session's explicit
throwaway-prototype exception still applies: fixture arithmetic and actual
browser checks replace per-test red/green user handoffs. Production TDD remains
unchanged. This continues the same prototype; it does not promote it.

## Confirmed in this round

The user approved Simple as the default: month, income, spending, money left,
a short category list, and transactions only when a category is opened.
Advanced has a separate Checks tab containing reconciliation, missing labels,
and other diagnostic work. Both modes retain a quiet incomplete-figures note
with an explanation available in Checks. Modes are display preferences, not
roles. The user also requested continued English WIP comments on #11.

## One implementation phase

Carry the prototype forward and implement the complete second-round experience
inside `prototypes/dashboard-11/`. Retain current charts, account selection,
category investigation and experimental budgeting where appropriate, with the
last in Advanced and explicitly outside the accepted first-delivery scope.
Do not delete prior feedback or present new user-testing results as observed.

Stable contracts and acceptance criteria:

1. `Enkel / Avanceret` changes only presentation. Selected publication, month,
   accounts and financial values remain identical across the switch. Returning
   to Simple closes diagnostic/detail UI and restores a quiet overview.
2. Simple has the three summary figures, plain categories and on-demand
   category transactions. Advanced offers separate overview/details and
   `Kontrol` navigation for unknown money, adjustments, transfers and account
   evidence; checks must not appear on the everyday overview. Reuse existing
   drill-downs without expanding into editing.
3. Compact coverage/provisional labels still accompany all displayed measures,
   categories, trends and balances. A partial figure names incomplete accounts
   near the figure or in a compact shared coverage line clearly covering it.
   Missing is null/unknown, never zero. Quiet confirmed activity can be zero.
   The unknown-transaction note is separate from coverage and provisional state.
4. Reports and their trend/detail data belong to one selected publication.
   Model a current publication, an as-was past publication and an as-known-at
   past view. Advanced exposes selection. Any non-current view has a persistent
   named banner in both modes and an obvious return-to-current control.
   Use explicit fixture publication metadata and precomputed reports; never
   relabel the exact same fixture as different historical evidence. Historical
   provisional status is relative to its known_at; current synthetic time must
   be explicit. Update the footer consistently.
5. Reconcile `REPORT-SHAPE.md` with accepted Gold/analytics/publication rules:
   refund direction; category allocation amounts vs transaction amounts;
   adjustment without category; paired transfer group vs manually decided
   one-sided transfer; unmatched claim appears only as unknown in public DTOs;
   account evidence_through; nullable balance and coverage; publication identity
   on all report surfaces. Do not expose privileged review/lineage reasons.
   Keep it an API-neutral proposal requiring maintainer acceptance.
6. Add synthetic examples for one-sided transfer and unknown unmatched claim,
   while preserving/refining negative category spending (net refund), partial
   and no-data account-months, quiet months, current provisional month and a
   historical view. Check totals independently and ensure every account view
   stays consistent. Explain missing labels under Checks with the documented
   `budget review` / `budget decide` operator route (descriptive only, no execution).
7. Add a household-passphrase login/logout UI demonstration with an obvious
   fictional passphrase and explicit demo-only labeling. No real password,
   authentication backend, security claim, LAN binding or database. Keep this
   server on loopback and fixtures synthetic-only; do not read `imports/` or
   private local reports. Preserve private data on disk without loading it.
8. Update README, HANDOFF, SESSION and report proposal in English while the UI
   remains Danish. Preserve the prior handoff as history. Document precisely
   how to run, what differs from main/Gold, remaining user questions, a compact
   two-participant task script and what is still not validated. #11 stays open.

## Boundaries, checks and ownership

Astra owns this plan, issue comments, final review and CHECKPOINT.md. The worker
owns every other file under `prototypes/dashboard-11/`, including an implementation
report `ROUND-2-IMPLEMENTATION.md`. No changes outside this directory; no GitHub
writes, staging, commits, merges, pushes, workflow changes or dependency/config
changes. Do not read private data. Other tasks may be active: preserve their edits.

Verify fixture arithmetic with `py -3.12 prototypes/dashboard-11/check_fixtures.py`
(or the available uv Python equivalent), JavaScript syntax, relevant repository
Python quality commands from `docs/agents/code-quality.md`, and actual browser
interaction at phone and desktop sizes. Check mode/selection invariance, separated
Checks, drill-down/close, empty selection, publication coherence/banners, missing
versus zero, negative refunds, login demo/logout and retained budget isolation.
Use a free loopback port if 8011 is occupied; never stop another task's server.
Provide concrete commands/results and browser evidence. Keep any temporary QA
artifacts under the prototype or temp, with no private information.

On completion Astra reviews the actual patch and evidence once through spec and
quality/security lenses, then sends at most one consolidated correction request.
No full validation rerun without a concrete gap. Ask the maintainer to try the
screen and to review the DTO proposal; do not claim usability was validated.

Routing doctor: static-ready; root `gpt-6-astra`, role `astra_flash_builder`,
worker `deepseek/deepseek-v4.1-flash`, provider `DeepSeek API`. No paid routing
probe. Actual inference routing must be evidenced from host metadata or reported
unverified at handoff.
