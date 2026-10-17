## Prototype pass ready for trial — 28 September 2026

Implemented locally on `codex/prototype-11-round-2`:

- Enkel now exposes Beløb / Mod budget with elapsed-month markers. Reserve and
  savings reconciliation remain in Advanced; category details open on demand.
- Advanced Udvikling over tid adds Budgetteret and a category selector. Selecting
  a category shows its net spending and monthly expense budget. Missing months
  remain gaps; refunds remain negative; budget points only appear for the exact
  publication, account scope and months with a plan.
- Monthly expense plans exclude accumulated holiday reserves. Category zero
  labels refer only to categorized entries and retain coverage/provisional state.

One native DeepSeek V4.1 Flash worker implemented this pass; GPT-6 Astra reviewed
the patch and one correction. Fixture audit: 2,272 checks, plus a failing negative
control. JavaScript syntax and Python format/types/complexity passed. The six
previously documented Ruff findings remain unsuppressed, awaiting the owner’s
decision. Provider inference metadata remains unverified beyond static routing.

Astra verified the actual screen: Simple budget markers and hidden savings
reconciliation; furniture spending versus its plan; negative clothing refund;
missing versus zero months; single-account and historical budget isolation;
category reset; custom and invalid ranges; year-to-date recovery. Desktop 1280
and phone 390/320 layouts showed no document overflow, and no console errors or
warnings were reported. These are agent checks, not household usability results.

The maintainer explicitly included read-only budget comparison in the first
usable release, with targets maintained outside the dashboard; editing and
forecasting remain deferred. [Recorded on #2](https://github.com/ATherkel/budget/issues/2#issuecomment-5865909851).

The new fixed-expense / planned rådighedsbeløb requirement is tracked in
[#99](https://github.com/ATherkel/budget/issues/99), which links back to
[the finding and discussion here](https://github.com/ATherkel/budget/issues/11#issuecomment-5865951679).
It is not implemented as an invented category flag or dashboard calculation.

Recommended next step: use this iteration as the visual and behavioral reference,
resolve the production budget/report contracts and #99, then implement production
vertical slices with normal TDD. Preserve synthetic examples as acceptance
scenarios; do not promote the demo server/login or fixture calculations.

The work is uncommitted and unpublished; local preview is
`http://127.0.0.1:8011/`. Handoff and verification are in
`prototypes/dashboard-11/{HANDOFF,TRENDS-IMPLEMENTATION,CHECKPOINT}.md` locally.
#11 remains open pending household feedback and agreement on the report interface.

🤖 Generated with Codex (GPT-6 Astra)
