# Modular household dashboard: implementation specification

Tracker: https://github.com/ATherkel/budget/issues/100

Status: implementation plan with maintainer-confirmed scope, stack, test seams,
budget-history policy and navigation defaults, 28 September 2026. Production
contracts still require D0/D1 and #12 acceptance. This is a specification,
not authorization to begin production implementation. The latest prototype has
not yet been reviewed by the household; confidence in its direction is not a
completed usability trial.

Execution gate: this is the parent specification, not one large implementation
assignment. Start with #101. #102 follows its contract work; the production
tickets retain their explicit prerequisites and TDD review gates. The parent
ready-for-agent label does not authorize executing all children at once.

## Problem Statement

The household needs one trustworthy view of its finances that serves two readers.
An everyday reader wants a calm monthly overview and an understandable comparison
with the budget. The operator wants to investigate categories, accounts, history
and incomplete figures without placing that maintenance work in the everyday view.

The prototype explores this experience, but its synthetic report builder, demo
login, global browser state and experimental budget arithmetic are not production
architecture. Copying it wholesale would make financial policy and presentation
hard to maintain. The repository currently contains contracts and tooling, not an
implemented production analytics or presentation layer.

## Solution

Build a read-only Danish dashboard from reusable modules with narrow interfaces.
Financial interpretation belongs to Gold and analytics; presentation receives
finished reports. One shared selection of Publication, accounts and period drives
every view. Enkel is the default, with Avanceret providing trends, account details
and a separate Kontrol area. Switching modes changes the presentation, not values.

Deliver small, dependency-ordered slices. First settle the report and budget
contracts, then deliver the simple actuals view, investigation, comparisons and
history. Resolve fixed-expense treatment through #99 rather than inventing a
category-wide flag. Use the prototype as behavior and visual reference, not as
application infrastructure.

### Decision status and precedence

- **Confirmed:** user decisions recorded on #11 and #2, plus the requirements
  below explicitly identified as confirmed.
- **Inherited:** accepted domain rules and ADRs; this specification does not
  silently amend them. Gold contract 0.2 itself remains proposed pending #12.
- **Proposed:** engineering choices and defaults in this specification. Publishing
  a spec does not by itself record maintainer acceptance of an unresolved policy.
- **Blocked:** an explicitly named decision must be settled before its dependent
  implementation. A ready ticket with blockers is not permission to skip them.

The later first-release budget decision supersedes the old blanket exclusion of
budget targets. Earlier prototype statements that budget comparison is
Advanced-only are also superseded. The experimental reserve engine is not thereby
accepted. The latest prototype remains local and unpublished; older linked
branches do not contain all the latest changes.

## User Stories

1. As an everyday reader, I want Enkel to be the initial view, so that I can understand the month without navigating accounting work.
2. As an everyday reader, I want income, actual expenses and money left after all expenses, so that I can see the monthly result.
3. As an everyday reader, I want a short category list, so that I can see where spending went without a transaction ledger filling the page.
4. As an everyday reader, I want transactions only when I open a category, so that I can investigate one amount when needed.
5. As an everyday reader, I want Beløb and Mod budget in Enkel, so that I can compare spending with the plan without switching modes.
6. As an everyday reader, I want a quiet incomplete-figures note with an explanation link, so that uncertainty is visible without demanding maintenance work.
7. As an everyday reader, I want current-month figures marked provisional, so that I do not mistake month-to-date amounts for final results.
8. As an everyday reader, I want unknown amounts distinguished from zero, so that missing evidence is not reassuring by accident.
9. As an everyday reader, I want Danish labels and amount formatting, so that the dashboard feels familiar.
10. As a phone user, I want readable figures and usable controls without horizontal page scrolling, so that the dashboard works on my usual device.
11. As a keyboard or assistive-technology user, I want named controls, usable focus and chart alternatives, so that every core task is available without precise pointing or color recognition.
12. As a household member, I want to select any nonempty combination of imported shared and personal accounts, so that ownership does not constrain my view.
13. As a household member, I want mode changes to preserve the accounts, month and Publication, so that the same question keeps the same answer.
14. As an operator, I want Avanceret to expose overview, account details and Kontrol separately, so that investigating does not clutter the summary.
15. As an operator, I want Kontrol to show Unclassified money in, money out and count separately, so that opposite entries cannot hide each other.
16. As an operator, I want Adjustments and Transfers distinguishable from expenses, so that their effect is understandable.
17. As an operator, I want Coverage and Evidence through for individual accounts, so that I know which evidence is incomplete.
18. As an operator, I want bank-stated balances with their dates and unknown balances left unknown, so that an invented balance cannot look authoritative.
19. As an operator, I want reconciliations supplied by analytics, so that the screen explains the same numbers it displays.
20. As an operator, I want a description of the existing CLI correction route, so that I can resolve classifications without a new browser editing workflow.
21. As a household member, I want a monthly budget amount and variance per applicable category, so that I can see remaining budget or overspending.
22. As a household member, I want a calendar-time marker on current-month budget bars, so that I can roughly compare spending progress with the time passed.
23. As a household member, I want that marker explained as elapsed time rather than a forecast, so that uneven spending and delayed postings remain understandable.
24. As a household member, I want the full monthly target kept intact, so that the dashboard does not silently prorate my budget.
25. As a household member, I want missing or mismatched budgets shown as unavailable, so that they are not read as zero or borrowed from another account scope.
26. As a household member, I want overall trends to include Budgetteret alongside actual figures, so that I can compare expected and actual expenses over time.
27. As a household member, I want a category-filtered trend, so that I can investigate a heading such as Boligudstyr og møbler.
28. As a household member, I want year-to-date, rolling twelve-month and custom trend periods, so that I can examine both short and long patterns.
29. As a household member, I want an exact-value table for a chart, so that points remain understandable on a phone and with assistive technology.
30. As a household member, I want missing months left as gaps and Refunds allowed to make spending negative, so that the chart tells the truth.
31. As an operator, I want a category selector to include categories outside the currently selected month, so that past spending remains discoverable.
32. As an operator, I want invalidated selections reset visibly and invalid date ranges explained, so that navigation cannot silently show a different question.
33. As an operator, I want Current, As-was and As-known-at Publications distinguished, so that I can compare what was shown with what is known now.
34. As a household member, I want a persistent named historical-view banner and a return-to-current action in both modes, so that I never mistake history for the present.
35. As an operator, I want every partial page and drill-down pinned to the same Publication, so that a concurrent import cannot mix results.
36. As an operator, I want an unavailable retained Publication explained with an explicit route to current data, so that deleted results are not silently replaced.
37. As a household member, I want actual expenses split into fixed and other spending, so that I can understand committed and discretionary use of money.
38. As a household member, I want planned monthly rådighedsbeløb from planned take-home income minus planned fixed expenses, so that annual or quarterly commitments are represented in the monthly plan.
39. As a household member, I want rådighedsbeløb clearly separated from actual money left after all expenses, so that planned capacity is not confused with cash flow.
40. As an operator, I want fixed/other treatment to permit different treatment within one Category, so that mixed categories do not force incorrect assumptions.
41. As a household member, I want unresolved fixed/other treatment shown honestly, so that unidentified spending does not silently become other spending.
42. As a household member, I want a household-passphrase login and logout, so that private-home-network access follows the accepted operating policy.
43. As an operator, I want dashboard reads to use only the selected Profile's permitted reporting store, so that test and development cannot reach production accidentally.
44. As a maintainer, I want one owner for each calculation, selection rule and display convention, so that a change can be made locally and verified through a small interface.
45. As a maintainer, I want a new bank connector to leave analytics and presentation unchanged, so that the reporting design stays source-independent.
46. As a maintainer, I want implementation tickets with visible outcomes, dependencies and focused acceptance examples, so that work can be delivered and reviewed in manageable steps.
47. As a maintainer, I want selected-category carry-forward and earmarked savings retained as a future requirement, so that an earlier design decision is not lost when the first release is bounded.
48. As a household member, I want trends for both Category groups and individual Categories in one grouped selector, so that I can choose a useful level of detail without nested controls.
49. As an operator, I want future account-specific budgets supported by an explicit scope model, so that adding them later does not require rewriting the dashboard.

## Implementation Decisions

### Established financial and trust rules

- Use the glossary's Reporting boundary, Category allocation, Coverage,
  Publication and Manual decision concepts. An account-selection filter does
  not redefine the Reporting boundary or reclassify Transfer legs.
- Income and Expenses use transaction facts with Refunds netted into their
  Category's direction. Category totals and drill-down values use allocations.
  Never sum transaction and allocation facts together. Splits remain deferred,
  but drill-down identities and amounts must not preclude the accepted grain.
- Savings remains Income minus Expenses, equal to Net cash flow in this release.
  The everyday label describes money left after all expenses. Savings rate is
  null when income is nonpositive; its interface states ratio units explicitly.
- Transfers, Unclassified money and Adjustments are outside income and expense
  totals. Adjustments have no allocations. An unmatched Transfer claim is public
  Unclassified money, not a privileged review explanation.
- Missing balances stay null. Account activity identifies paired and manually
  one-sided Transfers using public evidence; do not invent a counterpart name
  or expose lineage to make the display more detailed.
- Coverage comes from Gold, not a new balance-chain calculation. Every measure
  retains its Coverage and contributing incomplete account-months. Compact
  shared coverage wording is acceptable when its scope is unmistakable; a
  partial household figure names the incomplete accounts near the figures.
- Provisional period, incomplete Coverage, Unclassified money, missing budgets
  and unresolved fixed/other treatment are different conditions. Do not collapse
  them into one boolean. Enkel uses quiet wording and an explanation link;
  Kontrol carries the numerical maintenance detail.
- A current period is always provisional using Europe/Copenhagen's date.
  Closed periods stay provisional until each imported account has an admitted
  export produced at least seven days after period end whose range includes the
  period's last day. The only exemption is an account never imported. Historical
  views use the Publication's known-at time. Transaction dates are not converted.
- Missing actuals stay unknown. An absent category can be zero only with complete
  applicable evidence, and means no categorized expense, not proof that nothing
  was spent. Negative category spending remains negative.

### Module design

The maintainer confirmed FastAPI with Jinja/HTMX and Plotly for charts. Keep
Plotly-specific configuration and client lifecycle inside the Trend chart module.
Normal forms and links should provide usable server-rendered behavior; HTMX
enhances interactions without owning a parallel financial state model.

These are responsibility boundaries, not a requirement for one class or package
per row. Prefer a small interface hiding substantial implementation. Extract
shared behavior where two real consumers use it; do not build a generic dashboard
framework, widget registry, event bus or one wrapper per template.

| Module | Owns and exposes | Must not own |
| --- | --- | --- |
| Report context | Validated Publication identity, selected account IDs, reporting period and explicit report reference date; passes the same context to all report reads | Financial formulas, HTML, storage paths from request parameters |
| Household reports | Monthly overview, category detail, trend series, account activity and public checks through an API-neutral report interface | HTTP request objects, templates, source files, privileged lineage |
| Budget plan publication | Validated, immutable plan inputs and their scope/history identity, after the policy decision | Browser state, rewriting transaction facts, inference from actual spending |
| Budget comparisons | Applicable targets, actuals, variance, availability and planned rådighedsbeløb after #99; returned as report fields | Reading mutable household files on a dashboard request, reserve-engine assumptions |
| Dashboard application | Authentication, request validation, Report context resolution, report calls, page/fragment responses and consistent failures | Re-summing financial data, direct Gold queries |
| View state and navigation | Mode, tab, period, account selection, category selection, open detail and return navigation; coherent transitions and stale-response protection | A second financial dataset or browser-persisted source of truth |
| Display modules | Shared amount/date formatting, trust labels, summary figures, category/budget rows, transaction lists, account summaries and explanation sections | Financial arithmetic, classification, fetching their own unrelated Publications |
| Trend chart | Rendering supplied series plus accessible exact-value table and labels; chart library lifecycle | Inferring missing values, aggregating facts, budget policy, choosing a Publication |
| Access and composition | Household session policy and construction of permitted reporting dependencies from the selected Profile | Import or decision commands reachable from the dashboard |

The production analytics adapter and synthetic report adapter satisfy the same
report interface. This is a useful seam because both are real consumers of the
contract. Gold access stays inside analytics. Presentation can be developed
against synthetic reports while the pipeline is being completed.

The maintainer confirmed that a Publication preserves the budget plan used with
it: edited targets take effect through a new Publication; an As-was view retains
its original targets; an As-known-at view captures the plan used when that view
is built, alongside the current interpretation of older data.

The existing architecture requires analytics to read Gold only and the dashboard
process to receive only Gold storage. Adding mutable budget-file reads to
presentation or analytics would contradict that design. The budget-contract
decision must either publish validated plan data with an immutable identity in
the permitted reporting store, or explicitly amend the architecture through an
ADR. The historical behavior above is accepted; the precise projection/schema
and migration proposal belong to D1 and #12.

### Report interface obligations

The proposed prototype report shape is input to the contract work, not the
accepted contract itself. Settle a compact request/response vocabulary before
code. Separate reports may share one context envelope; do not return every
transaction for every month just to render an overview.

The envelope identifies Publication, account selection, currency, period,
reference date, Coverage and provisional status. Reports supply exact monetary
values, measure definitions, reconciliation values and counts where displayed.
Category detail carries allocation identity and amount separately from its
transaction identity and amount. Account reports carry dated nullable balances
and Evidence through. Trend points carry their own trust state. Budget responses
carry plan identity, exact scope and availability reasons independently of actuals.

The contract work must resolve two upstream ambiguities explicitly: which public
Gold projection supplies admitted-export dates/ranges needed for provisional
status, and when an account report means a monthly closing snapshot versus a
latest bank-stated balance with its own date. Neither is permission for analytics
to read Silver or privileged lineage, or for presentation to manufacture evidence.

Use Decimal in Python and an explicit lossless money representation if serialized;
never use floating point for financial calculation. Geometry conversion for a
chart is allowed after the values are final, with exact text/table values retained.
Analytics supplies financial ratios and variances. Presentation may calculate
calendar progress and layout geometry; it may not derive a new financial measure.

Expected states include invalid selection, empty account selection, no data,
budget unavailable and Publication unavailable. Failure is not an empty successful
report. Do not display a stale result under a newly selected context.

### Everyday and advanced behavior

- Enkel defaults to Beløb. Mod budget is available in both modes. A mode switch
  preserves financial selections and the chosen comparison mode, closes detail
  overlays and returns to a calm summary. It is a display preference, not a role.
- Avanceret has Overblik, Detaljer and Kontrol. Trends and historical selection
  follow the advanced layout. A historical banner survives switching to Enkel.
- Categories disclose compact transaction/allocation detail on demand. Account
  details and checks remain independently navigable. All visible strings are
  Danish; technical names and tracker discussion remain English.
- Confirmed initial preference policy: keep mode in the active page/session only,
  start a fresh visit in Enkel, and store no financial payload in browser storage.
  Persistent mode preference can be added as a separate interaction decision.
- Confirmed initial selections: all imported accounts and the current month in
  Europe/Copenhagen. A historical view starts at its known-at month. Missing
  months remain visible as gaps rather than silently selecting a populated month.
- Proposed initial navigation policy: validate selections centrally, preserve
  them in navigation, support ordinary browser back/forward behavior, and exclude
  amounts/descriptions from navigation URLs. No account selected shows a clear
  selection prompt, never a household total that pretends to be zero.

### Budget and trends

- Read-only budget comparison in the first usable release is confirmed. The
  maintainer selected TOML household inputs and household-scoped monthly targets.
  Compare only the exact declared account scope; other selections keep actuals
  and say budget unavailable. Validation, effective-month details and public
  publication projections are specified in D1.
- Account-specific budgets are a confirmed future requirement, explicitly
  deferred. The budget interface must carry stable scope identity and account
  membership rather than hard-code a single all-accounts budget. Keep scope
  applicability in one module so future account plans do not require changes
  throughout presentation. Do not implement account targets now or choose their
  overlap/precedence rules silently; D1 records those extension questions.
- A budget applies only to its declared months, currency, account scope and
  historical context. Do not silently reuse a household budget for one account,
  extrapolate a missing month, or turn a missing target into zero. Explicit zero
  is distinct from missing. A partially specified plan must not be labelled a
  complete household budget.
- Ordinary targets compare monthly net expense with the full monthly expense
  plan. Carry-forward reserves and earmarked savings are not expense forecasts.
  The maintainer explicitly deferred carry-forward and earmarking until after
  the first release. Preserve selected-category-only carry-forward as the earlier
  product direction; its production financial contract remains to be specified.
- Current-month positive-target budget bars have an elapsed-calendar marker:
  day-of-month divided by days-in-month, e.g. September 14 is 14/30. Use the
  report's explicit reference date, not the latest transaction/import. Historical
  views use their known-at date. No marker on closed-month, amount-only,
  zero/missing-target or multi-month reserve bars. It conveys time, not a linear
  spending expectation. Preserve negative and over-budget exact amounts even
  when visual bar widths are bounded.
- Overall trends retain income, expenses and net cash flow plus Budgetteret for
  expenses. A selected expense Category group or Category compares its net
  expense and target. Availability is not restricted to the summary month;
  rollups use allocations and never add a group to its own member Categories.
- Missing points form gaps. Known zeroes and net Refunds remain visible. Budget
  styling is distinct from provisional actuals and does not depend only on color.
  Titles, point descriptions and the exact-value table reflect selected scope.
- Year-to-date, twelve-month and custom ranges use real calendar months including
  gaps. The maintainer confirmed the selected reporting month as the anchor,
  consistently across both default ranges.
- The maintainer confirmed both levels of Category group → Category in one
  grouped trend selector, with no additional nested drill-down control. This
  refines the earlier tentative deferral of subcategory exploration. Use stable
  domain IDs and the household taxonomy, not fixture names or a new hierarchy.
  Exact group-budget aggregation and partial-target handling are specified in D1.

### Fixed expenses and rådighedsbeløb

- The maintainer explicitly placed this work after the first usable release.
  #99 is a dependency of this follow-up, not a blocker for ordinary comparisons.
- The required figure is planned monthly take-home income minus planned monthly
  fixed expenses, with periodic commitments allocated to months. It is not
  actual current-month income minus current-month fixed postings and not a
  lending eligibility assessment.
- Also show actual fixed and other expenses, separately from the plan. Preserve
  existing actual money-left and Savings meanings. Unknown treatment must be
  explicit rather than silently assigned to other.
- #99 owns the unresolved decision mechanism, transaction/commitment connection,
  refund treatment, periodic allocation/rounding, scope and history semantics.
  Different transactions in one Category must be able to receive different
  treatment. No boolean on the entire Category may substitute for that decision.
- Exact placement of the new figures needs a small review of the first rendered
  production slice because the current prototype never implemented them.

### Access and implementation discipline

Preserve the accepted private-home-network operating policy: one household
passphrase stored as a scrypt hash outside the repository and synced inputs,
HttpOnly and SameSite=Strict session cookie, slowed failed logins, explicit
logout, development on loopback, and Profile-selected production binding.
The accepted plain-HTTP LAN tradeoff is not reopened here. Protect every financial
page and fragment; validate sessions server-side. Decide and document session
lifetime and invalidation before implementing access, without inventing user roles.
Only login/logout mutate session state; reporting routes cannot invoke imports,
Manual decisions, Publication builds or input editing. Rendered report strings
must be escaped; financial payloads and secrets must not enter application logs.

Follow normal production TDD, not the throwaway-prototype exception. Astra owns
scope, architecture and acceptance; one Flash 4.1 worker implements an approved
slice, with the repository's human red/green handoff retained. Do not batch all
future tests up front or let a worker self-approve the red phase. Each slice ends
in review/refactoring and the applicable quality gate. No automatic commits,
pushes, deployment, issue closure or workflow changes follow from this spec.

## Testing Decisions

The maintainer explicitly agreed these public test seams:

1. Presentation: public rendered pages and HTTP responses, using synthetic report
   fixtures. Assert visible behavior, selection continuity, access enforcement,
   errors and trust wording, not template filenames or private helper calls.
2. Analytics: the public report interface over synthetic Gold facts and snapshots.
   Assert independently worked expected financial results and availability
   semantics, not calls to private aggregation helpers. This seam is necessary
   because financial rules have consumers beyond a browser.

Use existing Gold repository/contract seams rather than inventing a seam for every
display module. No project-owned collaborator mocks; a synthetic adapter must
implement the real report contract and share contract examples with production.
There is no existing production test suite to copy. Prior art consists of the
Gold/publication scenarios, layer briefs, TDD workflow and prototype fixture audit;
the audit is design evidence, not a substitute for production tests.

Run application tests in-process with synthetic data and ephemeral test-profile
stores; never read production/development databases, imports or operator profile
environment variables. Browser interaction and visual QA use a separate loopback
development demo containing synthetic reports, preserving the operating rule
that the test profile is not served. Verify keyboard use, focus return, phone
320/390 and desktop layouts, exact chart tables and no document overflow.

Acceptance examples to distribute across the owning slices:

- Complete, partial, never-imported, outside-managed-period and confirmed-quiet
  account-months; provisional current and closed periods, including the exact
  seven-day/range rule and historical reference dates.
- Income Refund and expense Refund, negative category expense, Transfers across
  selected/unselected accounts, one-sided Transfer, unmatched claim, Adjustment,
  offsetting Unclassified amounts, nonpositive income and nullable balances.
- Same values through mode transitions; every nonempty account subset; explicit
  no-account prompt; visible category reset; invalid range; browser back/forward;
  stale fragment response cannot overwrite a newer context.
- Publication changes during a page session, retained history with genuinely
  different facts/interpretation, unavailable and legacy Publications; no silent
  substitution and no privileged lineage access.
- Exact/missing/zero/partial budget, wrong account scope, changed plan history,
  February/leap-year and month-end markers, overspending and net Refunds.
- Mixed fixed/other transactions within one Category, annual commitment before
  payment, refund of fixed expense, unknown treatment and changed historical plan,
  after #99 has independent expected outcomes.
- Login failure/throttling, session expiry/logout, protected fragment access,
  escaped transaction description, no financial values in logs, read-only store
  access and invalid Profile refusal.

For every behavior: agree the public seam, write one focused red test, show its
meaningful failure, wait for maintainer review, then implement green and review
refactoring. Run relevant tests and Python lint/format/types/complexity gates.
The six existing prototype lint findings are not permission for production
suppressions. No quality configuration is loosened by this plan.

## Out of Scope

- Promoting the prototype server, login, fixture builder or financial JavaScript.
- Browser imports, classification editing, budget editing, split authoring or
  privileged review tooling; forecasts, subscription detection and bank APIs.
- Investment valuation, debt calculations, FX conversion, lending assessments,
  internet-facing hosting and a general-purpose dashboard builder.
- Reimplementing the warehouse pipeline inside a dashboard ticket. Production
  hookup depends on the #12-approved Gold implementation and operating stack.
- Automatically accepting Gold 0.2, changing ADRs, closing #11/#12/#99, or
  claiming household usability verification that has not happened.
- Fixed/other expense treatment, planned rådighedsbeløb, carry-forward and earmarking
  are outside the first release, but retained as dependency-ordered follow-ups.

## Further Notes

### Delivery map

Each row is a bounded ticket with a visible outcome, an agreed test seam and its
own red/green slices. It is not a request to deliver the entire row in one test
or one unreviewed worker run. Independent rows may proceed only after their
own prerequisites are settled. Keep one Flash writer by default.

| Step | Outcome | Prerequisites | Completion evidence |
| --- | --- | --- | --- |
| [D0 · #101](https://github.com/ATherkel/budget/issues/101) | Specify report/context contracts and interaction defaults for #12 acceptance | Existing domain/ADR decisions | Typed vocabulary, independently worked examples, trust/error semantics, explicit taxonomy and range-anchor decisions |
| [D1 · #102](https://github.com/ATherkel/budget/issues/102) | Settle and publish monthly budget input/history contract | D0; coordinate #99 | Scope, effective months, immutable identity, validation, plan completeness and historical examples accepted; architecture reconciled |
| [D2 · #103](https://github.com/ATherkel/budget/issues/103) | Deliver authenticated app shell and empty states | D0, #12 readiness; session policy decision | Protected full/fragment responses, Profile guards, Danish responsive navigation, synthetic adapter, no financial routes bypass authentication |
| [D3 · #104](https://github.com/ATherkel/budget/issues/104) | Deliver trustworthy monthly actuals in Enkel | D0, D2 | Real analytics over synthetic Gold + rendered summary/category list; no financial arithmetic in presentation |
| [D4 · #105](https://github.com/ATherkel/budget/issues/105) | Deliver category investigation and shared detail navigation | [D3 · #104](https://github.com/ATherkel/budget/issues/104) | Allocation-based rows, refunds, open/close/focus, month/YTD scope and state preservation |
| [D5 · #106](https://github.com/ATherkel/budget/issues/106) | Deliver Avanceret accounts and Kontrol | D3; D4 detail modules where reused | Balances/activity, unknowns, adjustments, transfers and supplied reconciliations; no diagnostic leakage into Enkel |
| [D6 · #107](https://github.com/ATherkel/budget/issues/107) | Deliver monthly Mod budget and time markers | D1, D3, D4 | Correct targets/variances, null/zero/scope cases, truthful progress bars in both modes |
| [D7 · #108](https://github.com/ATherkel/budget/issues/108) | Deliver overall and category trends | D0, D3, D6 | Calendar gaps, signed actuals, planned series, range/category controls, exact-value table |
| [D8 · #109](https://github.com/ATherkel/budget/issues/109) | Deliver historical navigation and concurrency behavior | D3, D5, D7; publication repository available | Same pinned Publication across page/fragment/detail; historical banner/reference date; unavailable result handling |
| [D9 · #110](https://github.com/ATherkel/budget/issues/110), follow-up | Deliver fixed/other expenses and planned rådighedsbeløb after the first release | #99, D1, D3, D6 | Accepted policy projected through Gold/analytics and calm summary; unknown split and periodic commitments verified |
| [D10 · #111](https://github.com/ATherkel/budget/issues/111) | Integrate real reporting and complete first-release household acceptance | D2–D8, #12, production Gold/operations available | Real adapter parity, read-only startup, responsive/accessibility task trial, release checklist and documented limitations |
| [F1 · #112](https://github.com/ATherkel/budget/issues/112), follow-up | Specify selected-category carry-forward and earmarked savings | D1; prior #11 direction | Accepted reserve semantics, scope/history/refund cases and a separate implementation plan; no release-one dependency |

D8 adds the historical picker and integration scenarios; Publication pinning is
part of D0/D2/D3 from the start, never postponed until the history screen exists.
D10 integrates an already accepted warehouse; it does not absorb unfinished
Bronze/Silver/Gold implementation. D9 and F1 do not block D10. D0/D1 supply
contracts to #12; they do not wait for #12 to close before drafting those contracts.

### Decision gates and learning checkpoints

- D0: confirm report fields, ratio units and selection error semantics; translate
  the now-confirmed group/Category, account/month, mode and trend defaults into
  the interface without reopening the user decisions.
  Explain the transaction/allocation grain with one synthetic Refund example.
- D1: specify the confirmed TOML inputs and how plans enter immutable
  reporting history; show why a newly edited budget must not silently alter an
  As-was result. Coordinate planned commitments with #99 instead of designing
  two incompatible budget sources. Define periodic rounding there, not in UI.
- #99: owner resolves the actual fixed/other and planned-commitment model. This
  spec repeats the question only as a dependency; it creates no competing issue.
- D2: agree session expiry/invalidation; implement the confirmed default navigation.
- D9: review the calm placement of the new measures using one rendered example.
- D10: both household readers attempt the original overview/investigation/trust
  tasks independently. Record observed difficulty separately from reported
  preference. The user can adjust wording/layout during these small reviews.

Keep English WIP updates on #11 linking the spec, accepted decisions, implemented
slices, verification and actual household feedback. Preserve earlier comments
as history. #12 remains the cross-layer readiness decision and #2 the overall map.

### Sources and continuity

- [Dashboard exploration #11](https://github.com/ATherkel/budget/issues/11)
- [Latest verified prototype status](https://github.com/ATherkel/budget/issues/11#issuecomment-5869085716)
- [First-release budget scope](https://github.com/ATherkel/budget/issues/2#issuecomment-5865909851)
- [Origin of fixed-expense finding](https://github.com/ATherkel/budget/issues/11#issuecomment-5865951679)
- [Fixed-expense contract #99](https://github.com/ATherkel/budget/issues/99)
- [Cross-layer readiness #12](https://github.com/ATherkel/budget/issues/12)

Repository evidence inspected at base 59f732f2db3a5a03b1b6dcd3bd43427842457c65:
domain glossary, presentation/analytics/operations/publication contracts, accepted
ADRs, current prototype and its decision records. The local draft and tracker
spec should carry the same scope and dependency map.

🤖 Generated with Codex (GPT-6 Astra)
