# #11 — confirmed direction and handoff

## Status as of 17 September 2026

The maintainer confirms that the current prototype is a good direction and
wants further changes deferred to the real implementation. This prototype
iteration is frozen. The runnable version is preserved in commit `78efa47`;
subsequent changes to this handoff are documentation only.

Language convention: this handoff and GitHub comments are in English. The
dashboard interface remains in Danish; Danish UI labels appear below where
needed to identify the corresponding controls.

Branch: `codex/prototype-11-dashboard`. Launch from the repository root:

```powershell
py -3.12 prototypes/dashboard-11/serve.py
```

Open <http://127.0.0.1:8011/>. A fresh checkout works with the synthetic
reports alone. Private local reports and bank statements are not included
in the branch.

## What the feedback confirms

- The maintainer likes the current iteration as a starting point for implementation.
- A Danish interface, arbitrary account selection, trend charts, clear amount
  signs, and compact transaction rows are requirements raised during the session.
- Budget versus actual spending and earmarked reserves are desired features.
  Only selected categories should carry remaining amounts forward. Other
  categories' underspending and overspending affect general savings.

This confirms the direction. Independent completion of all three original
tasks by both participants has not been documented. Full understanding of
incomplete figures must not be marked as validated.

## Feedback from the second participant

The maintainer relays his wife's experience: there are many numbers and
transactions, and the missing-category section at the bottom is unclear.
He therefore wants a choice between simple and advanced views and takes
responsibility for reconciliation himself. This is relayed feedback, not
directly observed task completion.

## Implementation requirement: Simple / Advanced

The user requested the toggle itself; the grouping below is an implementation
proposal that has not yet been tested. The Danish UI labels are **Enkel** and
**Avanceret**.

- **Simple** is proposed as the default: month, account selection, income,
  expenses, money left after expenses, categories, and chart. Transactions
  open on demand. Long lists of unclassified amounts, adjustments, internal
  transfers, and reconciliation details are hidden from the overview itself.
- **Advanced** shows the underlying account coverage, unclassified money
  in/out and counts, adjustments, transfers, and account activity. The report
  remains read-only.
- **Both** must briefly and visibly indicate provisional or incomplete figures,
  with access to the explanation. This is an existing trust requirement from
  the presentation layer. Hidden details must not make incomplete figures
  appear final.
- The same account and period selection must yield the same financial values
  in both views. The toggle changes detail level, not classification or arithmetic.
- The choice is a display preference available to any user, not a role, gender,
  or access restriction. Whether to persist the preference remains undecided.

Acceptance scenarios for the normal TDD process: switching without changing
figures or losing account selection; incomplete and unclassified conditions
still flagged in Simple; details accessible in Advanced; subsequent testing
of whether both participants understand the simpler view.

## From prototype to real application

1. Use this branch as a reference for behavior and presentation. Implement the
   real application on a new branch from the agreed production/integration base.
   The prototype server and fixed account combinations must not become the
   production reporting engine.
2. Agree on the concrete analytics interface using
   [REPORT-SHAPE.md](REPORT-SHAPE.md). It remains a proposal. Arithmetic,
   classification, and coverage belong in their respective layers; the screen
   receives completed reports and renders them.
3. Build the monthly overview, category investigation, and trust indicators
   with Simple/Advanced using the repository's normal TDD handoffs.
4. Use [SESSION.md](SESSION.md) as the feedback history and the examples as
   acceptance scenarios. Repeat the original three tasks on the implementation.
5. Make a separate scope decision for budgeting and earmarked savings before
   implementing them: #2 still excludes budget targets from the first delivery.
   The newly requested savings-after-earmarking measure must not replace the
   accepted analytics measure Savings = Income − Expenses without an explicit
   decision.

## Unresolved, not approved through this iteration

- Simple/Advanced is neither implemented nor user-tested in the frozen prototype.
- Budget scope under account selection, negative reserves, opening reserves,
  changed budgets, and actual use of accumulated vacation funds remain untested.
- Earmarking in the tool may replace a dedicated vacation account; the intention
  is confirmed, but this has not been demonstrated as a complete workflow.
- Import, configuration, and recovery in #10, and warehouse readiness, are not
  settled here. The existing screen does not resolve missing categories.
- Checked on 17 September: #16, #18, and #20 were open and unmerged.
  #16 documents decisions from #5; proposals in #18/#20 were not accepted
  through the prototype. #2 and #11 remained open at handoff.

This record does not automatically authorize production promotion, a merge,
or closure of #11. It preserves the maintainer's confirmation and the next
concrete requirement.
