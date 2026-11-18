---
type: architecture
---
# Presentation Layer

## Purpose

Render household financial information for phone and desktop browsers. The
dashboard is in Danish, supports keyboard use, and shows loading, empty,
unavailable and request-failure states.

## Boundary

Presentation consumes analytics reports only, as defined in
[`report-contract.md`](report-contract.md). It does not classify
transactions, calculate financial totals, or access source data. It never
reads Gold either: it names the publication in the report context, and
analytics opens it.

Presentation owns the interaction around a report: pinning the resolved
context on the page, keeping a response eligible only for the activity that
asked for it, restoring the selection on browser back and forward, and the
empty-selection prompt. The rules are in
[`report-contract.md`](report-contract.md#navigation-and-selection-transitions).

## Initial Technology Direction

- FastAPI for the HTTP application.
- Jinja templates and HTMX for server-rendered interactions.
- Plotly for charts where a chart improves comprehension.

This is a direction, not an implementation commitment; a technology change
must preserve the analytics-facing DTO boundary.

## Initial Screens

- Current-month overview: income, expenses, savings, savings rate.
- Category view: current month and year-to-date spending.
- Account activity: balances and transfer activity.
- Trend view: month-over-month totals.

## Enkel and Avanceret

This is the display-mode contract for
[issue #294](https://github.com/ATherkel/budget/issues/294). It consolidates the
recorded decisions below; it does not implement the deferred screens or accept
their prototype report shapes. The shell remains Enkel-only until #106 delivers
a working Avanceret screen. Add the switch with that screen, never as a dead
control, and expose only implemented tabs and features.

### Screen and figure ownership

Avanceret combines a richer version of the shared overview with separate
investigation screens. It is not a second set of financial calculations or an
access role. Both modes are available to the same authenticated household reader.
For the same report context, shared figures have identical values and trust
semantics. Presentation reuses analytics reports and shared display modules.

| Surface | Enkel | Avanceret | Delivery owner |
| --- | --- | --- | --- |
| Monthly summary | Income, Expenses, money left, and Ukategoriseret Ind/Ud; every Category row in report order | The same summary and Categories in **Overblik** | #104 and #380; accepted monthly report contract |
| Category investigation | Transactions/allocation details on demand, not a ledger in the overview | The same on-demand investigation from Overblik | #105, including month/YTD semantics |
| Monthly comparison | Beløb by default; Mod budget when delivered | The same choice in Overblik, with the same applicable targets and variance | #102 and #107 |
| Trends | No trend panel in the calm overview | Udvikling over tid in Overblik: actuals and applicable Budgetteret series, grouped Category selector, range controls and exact-value table | #108 |
| Account activity | No account ledger or balance panel; shared account selection remains available | **Detaljer**: dated nullable bank balances, Evidence through, account Coverage and activity, including public Transfer and Adjustment detail | #106 |
| Diagnostics | Compact trust notes and the existing basic explanation; no diagnostic counts or reconciliation | **Kontrol**: Coverage reasons and incomplete account-months, provisional reasons, Unclassified money in/out/count, Adjustments, public Transfer evidence and analytics-supplied reconciliation | #106 |
| Historical navigation | Keep the named historical banner and return-to-current action when viewing history | Publication picker in the advanced controls; banner and return-to-current action remain visible | #109; existing pinning and superseded-publication rules already apply |

Ukategoriseret is deliberately present in both summaries: #380 supersedes the
older #100/#106 wording that hid its amounts from Enkel. Ind and Ud stay separate
and signed; neither is added to money left. The count remains in Kontrol. The
basic explanation still shows neither those amounts nor their count, as specified
in [the monthly report contract](report-contract.md#monthlyoverview).
Likewise, the accepted requirement to show every Category row supersedes the
prototype's short-list proposal. A savings rate is not an additional requirement
of this mode decision; existing report fields and display rules govern it.

Detaljer explains account activity; Kontrol explains confidence and reconciliation.
They may reuse the same public detail modules. Neither may infer a missing
Transfer counterpart, disclose privileged lineage, or run an operator command.
The correction route is descriptive guidance to `budget review` / `budget decide`,
not a dashboard execution or editing endpoint, and remains separate from #155's
operator stages. Unknown balances and unsupported counts remain unknown.

Fixed/other spending and planned rådighedsbeløb remain with #99/#110; carry-forward,
earmarking and the prototype's savings-after-earmarking arithmetic remain with
#112. Their presence in a prototype does not add them to #106 or this contract.

### Switching and navigation

- Place one labelled **Enkel / Avanceret** control in the shared page controls,
  below the page heading/month control and above the account selector and screen
  content, following the prototype's mode bar. Keep it reachable in both modes
  and at phone widths, with keyboard access and an exposed selected state.
- A fresh visit starts in Enkel and Beløb. Keep the selected mode during the
  active visit/session, including ordinary links, forms, account/month changes,
  tab changes and detail navigation. Do not save a lasting preference that makes
  a fresh visit start in Avanceret.
- An explicit mode switch closes open detail overlays and goes to the calm
  summary: Enkel's overview or Avanceret's Overblik. Preserve the accounts,
  reporting month, pinned Publication and reference date, and Beløb/Mod budget
  choice. Switching back to Avanceret does not resume a previous Kontrol tab.
- Overblik, Detaljer and Kontrol are independently navigable within Avanceret.
  Changing tabs preserves the shared context. A deliberate explanation link to
  Kontrol is a targeted navigation: it opens Avanceret/Kontrol at the relevant
  context rather than applying the generic switch's Overblik destination. Keep
  the existing basic explanation usable before Kontrol ships and retain an
  explicit route back to the originating view once it does.
- Browser back/forward restores the entry's mode and destination, rather than
  applying the explicit-switch reset. Entries carry the active tab and applicable
  comparison/detail return state alongside the selection already required by the
  [navigation contract](report-contract.md#navigation-and-selection-transitions).
  Restore and validate the pinned context under a fresh request generation.
  Stale responses, empty selections and unavailable Publications follow that
  contract unchanged; no financial payload enters history or browser storage.

### Evidence and design inferences

- **Recorded decisions:** the [26 September #11 feedback](https://github.com/ATherkel/budget/issues/11#issuecomment-5848770964)
  confirms Enkel by default, separate Kontrol, quiet trust wording and unchanged
  selections/values. The [28 September follow-up](https://github.com/ATherkel/budget/issues/11#issuecomment-5865881399)
  requests Mod budget in Enkel too. [#100](https://github.com/ATherkel/budget/issues/100),
  under Everyday and advanced behavior, names the three tabs, advanced trends
  and history, session-only preference, preserved comparison choice and the
  summary destination after switching. Its later scope amendments govern delivery.
- **Prototype evidence:** [index.html](../../prototypes/dashboard-11/index.html)
  places the switch above accounts and tabs; [app.js](../../prototypes/dashboard-11/app.js)
  renders separate overview/details/checks panels, closes detail on mode changes
  and targets Kontrol from the explanation. The
  [archive notes](../../prototypes/dashboard-11/README.md) and
  [original handoff](https://github.com/ATherkel/budget/blob/f46bc63524e2df8c86c37ba8ed2906dda94143d0/prototypes/dashboard-11/HANDOFF.md)
  distinguish exploratory behavior from accepted financial policy. The original
  handoff predates the mode implementation and subsequent decisions.
- **Inferences made concrete here:** adopt the prototype's shared control placement
  and Overblik trend placement; restore the active tab on history navigation and
  retain the originating view for targeted Kontrol navigation. These complete the
  recorded context-preservation requirement; they are not claims that the
  prototype implements browser history or that the household tested these flows.
- **Precedence:** current report contracts and later decisions, including
  [#380](https://github.com/ATherkel/budget/issues/380), override older prototype
  wording. This decision does not claim a completed Avanceret household trial.

### Acceptance examples for delivery

1. From Enkel with one account, month M and Publication P selected, switch to
   Avanceret. Overblik shows the same summary values, every Category row and
   trust state, using the same reference date. With Mod budget selected, the
   comparison choice and applicable values also survive.
2. Open Detaljer, then Kontrol, then switch to Enkel. Diagnostic counts and
   reconciliation disappear; Ukategoriseret Ind/Ud and required trust notes
   remain. Switch to Avanceret again: land on Overblik, with overlays closed.
3. Follow an explanation link into Kontrol, then return or use browser Back.
   Restore the originating mode and selection. Forward restores Kontrol and its
   context; it does not land on Overblik or select a newer Publication.
4. Change accounts or month in Kontrol: stay in Avanceret/Kontrol. Clear all
   accounts: show the selection prompt, with no stale figures. A mode switch or
   history restoration cannot resurrect a late response or replace an unavailable
   Publication silently.
5. A fresh visit starts in Enkel. A restored history entry remains in its recorded
   mode. Before #106 ships, the shell has no Avanceret switch or empty tabs;
   after it ships, undelivered trends, budgets and history controls remain absent.

These are implementation acceptance criteria, not new report DTOs. #106 must
still settle its approved balance, Transfer, Evidence through and reconciliation
examples in [the report contract](report-contract.md), as required by
[#106](https://github.com/ATherkel/budget/issues/106),
before application implementation.

## Data Trust Display

- Any report period that includes the current, still-accumulating calendar
  month always carries a visible provisional/month-to-date label at the point
  of display — not just a documented caveat, and with no exception. Which month
  is current is decided from today's date in Europe/Copenhagen;
  `transaction_date` itself is never converted. A household that is behind on
  its imports has *more* reason to see the label, not less, so no coverage
  status withholds it here.
- A period that is already closed carries the same label until, for every
  account in the report and *every month* in the period, one of the exports
  counted in the account's evidence ranges was produced at least the
  late-booking window (7 days unless the profile sets another) after
  that month ended *and* its range covers that month's last day. Late bookings
  land on their transaction date, so an export starting after a month cannot
  show them, however late it was produced. Checking every month, not only the
  period's last, keeps a year-to-date total provisional while one of its
  months can still change. Gold publishes the per-account, per-month
  half of this rule as `MonthlyBalanceSnapshot.late_bookings_settled`;
  analytics adds the current month and returns the label with the report.
  This bullet and the one above are the only statement of the rule; other
  documents cite them.
- Exactly one account is exempt from holding the label on a closed period: one
  that has never been imported, meaning its `GoldAccount.evidence_through` is
  null. It already reports `no_data` on its own line, and no export of it is
  outstanding, so it cannot be what the period is waiting for. The exemption is
  written on `evidence_through`, never on the period's coverage status: an
  account that *has* been imported reads `no_data` for any period its evidence
  does not reach, and a later export can still reach back and change that
  period — which is precisely what the label warns about.
- Known first-release limitation: an imported account with no booked
  transaction yet has no managed period, so no snapshot rows carry its flag
  and it cannot hold the label either. Its first booked transaction creates
  its rows, and reports restate.
- Every screen reads exactly one Gold publication, and all requests from one
  page read the same one. A screen showing any publication other than the
  current one carries a visible banner naming it (its label, and whether it is
  an as-was or as-known-at view). A past view takes the provisional label as
  of the publication's `known_at`, not today
  ([`publications.md`](publications.md)). How the picker and banner look is
  pending: [#109](https://github.com/ATherkel/budget/issues/109).
- A page opened on the current publication keeps reading it after a newer
  build becomes current, so its parts never mix two publications. That is a
  superseded page, not a past view: instead of the banner, it says that newer
  figures exist and offers a reload. When its result is no longer retained,
  the page offers the current publication explicitly and never substitutes it
  ([`report-contract.md`](report-contract.md#reportpublication)).
- Account and balance views must reflect each account's coverage status from
  analytics; a `partial` or `no_data` account must never render as if its
  balance or totals are complete.
- Every screen that shows a household-level measure (overview, category, and
  trend views) must display the coverage the report carries for it. A
  `partial` total names the accounts that are not complete.

## Non-Responsibilities

- Importing or editing raw bank data.
- Making categorization decisions.
- Using browser-stored financial data as a system of record.
