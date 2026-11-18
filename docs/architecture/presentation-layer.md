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

Avanceret combines a richer shared overview with separate investigation screens:
**Overblik**, **Detaljer** and **Kontrol**. Both modes are available to the same
authenticated household reader; mode is a presentation preference, not an access
role. Both summaries use the same
[monthly overview report](report-contract.md#monthlyoverview), including its
figure visibility and Category display rules.

The mode switch and advanced screens are pending:
[#106](https://github.com/ATherkel/budget/issues/106). Until a working advanced
screen is delivered, the shell remains Enkel-only. Expose only implemented tabs
and features, never dead controls.

### Screen ownership

| Surface | Enkel | Avanceret | Contract or pending delivery |
| --- | --- | --- | --- |
| Monthly summary | Monthly overview | The same overview in **Overblik** | [MonthlyOverview](report-contract.md#monthlyoverview) |
| Category investigation | On-demand detail, not a ledger in the overview | The same investigation from Overblik | [Spending detail](report-contract.md#spendingdetail) |
| Monthly comparison | Beløb by default; Mod budget when delivered | The same choice in Overblik | Pending: [budget inputs](https://github.com/ATherkel/budget/issues/102) and [comparison](https://github.com/ATherkel/budget/issues/107) |
| Trends | No trend panel in the calm overview | Udvikling over tid in Overblik, with its range and Category controls and exact-value table | Pending: [trends](https://github.com/ATherkel/budget/issues/108) |
| Account activity | Shared account selection, without an account ledger or balance panel | **Detaljer**: dated bank balances, Evidence through, account Coverage and activity, public Transfer and Adjustment detail | Pending: [account activity](https://github.com/ATherkel/budget/issues/106) |
| Diagnostics | Compact trust notes and the basic explanation | **Kontrol**: Coverage and provisional reasons, incomplete account-months, Unclassified money, Adjustments, public Transfer evidence and reconciliation | Pending: [Kontrol](https://github.com/ATherkel/budget/issues/106) |
| Historical navigation | Historical banner and return-to-current action remain visible | Publication picker in the advanced controls, with the same banner and return action | [Data trust display](#data-trust-display); picker pending: [historical navigation](https://github.com/ATherkel/budget/issues/109) |

Detaljer explains account activity; Kontrol explains confidence and reconciliation.
They reuse public detail modules and remain read-only. Operator correction guidance
is descriptive, without a dashboard execution or editing endpoint; operator stages
are a separate pending workflow: [operator stages](https://github.com/ATherkel/budget/issues/155).

Additional measures are pending separate contracts and are not introduced by these
modes: [fixed/other spending and planned rådighedsbeløb](https://github.com/ATherkel/budget/issues/110),
subject to [their design](https://github.com/ATherkel/budget/issues/99), and
[carry-forward and earmarking](https://github.com/ATherkel/budget/issues/112).
Account and diagnostic implementation remains gated on approved balance, Transfer,
Evidence through and reconciliation examples in the [report contract](report-contract.md),
pending [the account and Kontrol contract](https://github.com/ATherkel/budget/issues/106).

### Switching and navigation

- Place one labelled **Enkel / Avanceret** control below the page heading/month
  control and above the account selector and screen content. Keep it reachable
  in both modes and at phone widths, with keyboard access and an exposed selected
  state.
- A fresh visit starts in Enkel and Beløb. Keep the selected mode during the
  active visit/session, including ordinary links, forms, account/month changes,
  tab changes and detail navigation. Do not save a lasting preference that makes
  a fresh visit start in Avanceret.
- An explicit mode switch closes open detail overlays and goes to the calm
  summary: Enkel's overview or Avanceret's Overblik. Preserve the shared report
  context and Beløb/Mod budget choice. Switching back to Avanceret does not resume
  a previous Kontrol tab.
- Overblik, Detaljer and Kontrol are independently navigable within Avanceret.
  A deliberate explanation link to Kontrol opens Avanceret/Kontrol at the relevant
  context rather than applying the generic switch's Overblik destination. Keep
  the basic explanation usable before Kontrol ships and retain an explicit route
  back to the originating view once it does.
- Browser back/forward restores the entry's mode and destination, rather than
  applying the explicit-switch reset. Entries carry the active tab and applicable
  comparison/detail return state alongside the selection required by the
  [navigation contract](report-contract.md#navigation-and-selection-transitions).
  That contract governs context preservation, validation, response eligibility,
  empty selections, unavailable Publications and browser storage for both modes.

### Mode transition examples

- From Enkel with a selected report context, switch to Avanceret: land on Overblik
  with the same summary and comparison choice. From Kontrol, switch to Enkel and
  then to Avanceret: land on Overblik with detail overlays closed.
- Follow an explanation link into Kontrol, then return or use browser Back:
  restore the originating mode and selection. Forward restores Kontrol, not
  Overblik. Account/month changes within Kontrol keep Avanceret/Kontrol selected.
- A fresh visit starts in Enkel; a restored history entry keeps its recorded mode.
  Undelivered features have no controls, even after the mode switch is available.

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
