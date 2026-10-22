## From prototype to implementation plan — 28 September 2026

The maintainer requested conversion of the prototype and discussion into an
implementable, modular specification using to-spec. The result is
[#100: Implement the modular household dashboard from the #11 prototype](https://github.com/ATherkel/budget/issues/100),
with ten bounded first-release steps and two follow-ups. Each has an outcome,
module responsibilities, public test seams, acceptance examples and prerequisites.

The maintainer has not yet tried the latest prototype. His confidence in the
direction is recorded as feedback, not a completed household usability trial.
The prototype remains a visual/behavioral reference; no demo code is promoted.

New decisions confirmed during specification:

- FastAPI + Jinja/HTMX, with Plotly isolated in its chart module.
- Presentation tested through rendered pages/HTTP responses; financial behavior
  through the public analytics report interface over synthetic Gold data.
- First-release budgets are household-scoped monthly targets authored in TOML.
  Exact declared scope must match the selected accounts; unavailable comparisons
  are not guessed. Account-specific budgets are a **confirmed future requirement**,
  so scope is explicit in the interface, while their implementation is deferred.
- A Publication preserves its plan. Target edits enter a new Publication;
  As-was retains original targets; As-known-at captures the plan used when built.
- Trends support both Category groups and individual Categories in one grouped
  selector, without an additional nested control.
- Initial defaults: all imported accounts, the current Copenhagen month, Enkel
  on a fresh visit, and trend ranges anchored to the selected reporting month.
  Historical views start at their known-at month; missing months remain gaps.
- Actual fixed/other expenses and planned monthly rådighedsbeløb are **after the
  first release**. #99 remains their design prerequisite; implementation is #110.
- Selected-category carry-forward and earmarking are also **after the first
  release**, with their specification retained in #112.

The module design centralizes financial reports, Report context and view-state
transitions, shared display modules, budget applicability and chart rendering.
It explicitly prohibits duplicated totals in templates/browser code, direct
Gold access from presentation, and a generic dashboard framework built in advance
of real consumers.

Next actionable work is #101 (report/context contract), followed by #102
(budget input/publication contract), feeding the existing #12 readiness review.
Their output includes public late-booking evidence, balance-date semantics,
plan completeness and immutable budget projections. Those are contract questions,
not UI implementation guesses. Normal production TDD and its human red/green
handoffs remain in force; Astra orchestrates and Flash 4.1 implements approved
slices. Implementation tickets are not marked ready while prerequisites remain.

No production application code, commits, pushes or deployment were made. #11,
#12 and #99 remain open. Future implementation and observed usability results
should continue this timeline.

🤖 Generated with Codex (GPT-6 Astra)
