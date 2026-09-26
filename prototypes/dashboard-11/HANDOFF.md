# #11 — confirmed direction and handoff

## Status as of 26 September 2026

🤖 Added by Claude Code (Claude Opus 5.5)

The maintainer will run a second prototype round before #11 closes. This
section records what changed after the freeze and what that round needs to
settle. The 17 September record below is unchanged; where the two disagree,
this section is current. Document links point at `main` as of
[`b1285e5`](https://github.com/ATherkel/budget/tree/b1285e5431995cec838da888364ac2925b4c3fe5).

### Stale statements in the 17 September record

- #16, #18 and #20 are merged (17, 18 and 23 September), and their ADRs are
  accepted.
- #10 is closed, resolved by #58 (ADR-015 and `operations.md`). Missing
  categories are settled outside the dashboard with `budget review` and
  `budget decide`, so the dashboard can name that route instead of saying the
  workflow is undecided.

### Resolution evidence

| #11 asks for | Status |
| --- | --- |
| A linked throwaway prototype | Done: this branch, UI at `78efa47`. |
| Live maintainer feedback | Done: [SESSION.md](SESSION.md). Neither participant has completed the three tasks on their own, and the second participant's feedback is relayed. |
| Agreed screen behavior | Partly: the direction is agreed. Simple/Advanced is untested, and the missing-category section is unclear. |
| Analytics-facing interface requirements | Open: [REPORT-SHAPE.md](REPORT-SHAPE.md) is a proposal and predates Gold 0.2. |

### Decisions merged after the freeze

- **Gold contract 0.2** (#18; ADR-007, ADR-008): a `refund` type; `adjustment`
  transactions carry no category; `transfer_group_id` joins the two legs of a
  paired transfer; `GoldAccount.evidence_through`; Gold publishes coverage on
  each monthly balance snapshot ([gold-contract.md]).
- **Classification and transfers** (#20; ADR-011, ADR-012): a transfer claim
  with no counterpart stays `unknown` with an `unmatched-transfer` review item.
  A one-sided transfer is a `transfer` with no group and comes only from a
  manual decision ([classification.md]).
- **Publications** (#57; ADR-014): every page reads exactly one Gold
  publication, and past reports come as *as-was* or *as-known-at*
  ([publications.md]).
- **Operations** (#58; ADR-015): `budget serve` runs on the home network behind
  one household passphrase and opens `gold.db` read-only ([operations.md]).

### Work the later docs assign to #11

- The publication picker, and a banner on any non-current publication naming
  its label and whether it is as-was or as-known-at. A past view takes the
  provisional label as of the publication's `known_at` ([presentation-layer.md],
  [publications.md], ADR-014).
- The login page ([operations.md]).
- Coverage on every household-level measure, where a `partial` total names its
  incomplete accounts. The provisional label is always on the current month,
  and stays on a closed month until every imported account has an admitted
  export produced at least 7 days after month end that covers its last day
  ([presentation-layer.md]).
- The styling of negative category spending, a net refund
  ([analytics-layer.md]).

The frozen prototype has neither a picker, a banner nor a login page. It shows
coverage and a provisional flag, but those rules were written after it.

### Scenario gaps

The synthetic data has one paired transfer and no other transfer case. Add:

- A one-sided transfer: a `transfer` with no `transfer_group_id`.
- An unmatched transfer claim. It reaches the dashboard as `unknown`, because
  its review item lives in Gold's privileged lineage interface, which analytics
  may not read. Whether the Unclassified section can explain a leg that waits
  for the next import is open. If it needs a contract change, it belongs to
  #12.

### Second round

1. Reconcile REPORT-SHAPE.md with Gold 0.2 and [analytics-layer.md], and ask
   the maintainer to accept it as the analytics interface requirements.
2. Add the publication picker and banner, the login page and the transfer cases
   above, and point the missing-category section at `budget review`.
3. Add Simple/Advanced, and have both participants run the three original
   tasks in both modes.
4. Post the resolution comment on #11, close it, and add a pointer to #2's
   Decisions so far.

Budgeting and earmarked savings stay out: #2 excludes budget targets, so they
need a separate scope decision rather than a #11 closure. If the maintainer
instead closes #11 on the 17 September confirmation, the picker, banner and
login page must first move explicitly to #12 or an implementation ticket.

[analytics-layer.md]: https://github.com/ATherkel/budget/blob/b1285e5431995cec838da888364ac2925b4c3fe5/docs/architecture/analytics-layer.md
[classification.md]: https://github.com/ATherkel/budget/blob/b1285e5431995cec838da888364ac2925b4c3fe5/docs/architecture/classification.md
[gold-contract.md]: https://github.com/ATherkel/budget/blob/b1285e5431995cec838da888364ac2925b4c3fe5/docs/architecture/gold-contract.md
[operations.md]: https://github.com/ATherkel/budget/blob/b1285e5431995cec838da888364ac2925b4c3fe5/docs/architecture/operations.md#dashboard-access
[presentation-layer.md]: https://github.com/ATherkel/budget/blob/b1285e5431995cec838da888364ac2925b4c3fe5/docs/architecture/presentation-layer.md#data-trust-display
[publications.md]: https://github.com/ATherkel/budget/blob/b1285e5431995cec838da888364ac2925b4c3fe5/docs/architecture/publications.md#past-views

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
