# ADR-011: Classify by Manual Decision, Then Transfer Pairing, Then Rules

**Status:** Proposed

## Context

Gold gives every booked transaction a type and, for income, expense, and
refund, a category. Four sources could supply it: household-authored rules,
manual decisions, pairing transfer legs across accounts, and the bank's own
category labels.

The bank labels do not match household meaning. In the private samples they
file transfers under the bank's income and expense groups and returned goods
under income, and leave roughly one row in ten uncategorised.

A plausible but wrong classification is worse than a visible unknown: it
silently moves money between totals, while an `unknown` counts as unclassified
and raises a review item. Raised in
[issue #7](https://github.com/ATherkel/budget/issues/7).

## Decision

- **Precedence.** An applicable manual decision wins; otherwise a transfer
  pair ([ADR-012](ADR-012-transfer-evidence.md)); otherwise the
  highest-priority rule result; otherwise `unknown`.
- **Rules look at one transaction only**: its account, description text,
  amount, transaction date, and the bank's category labels.
- **A rule assigns a category, a transfer claim, or an adjustment with a
  reason.** For a category, the type follows from the category's direction and
  the amount's sign: a negative amount in an expense category is `expense` and
  a positive one `refund`; a positive amount in an income category is `income`
  and a negative one `refund`, preserving issue #4's returned-income netting.
  A zero amount is a sign mismatch and stays `unknown`.
- **Priority, not file order.** Every rule has an integer priority, 0 by
  default. The highest-priority matching rules decide; if they disagree, the
  transaction stays `unknown` with a conflict review item.
- **Bank category labels are provenance.** A rule may test them. They are never
  copied into Gold and never used as a fallback.
- **Manual decisions target transaction identifiers**, which survive
  re-imports and rebuilds. A decision whose target disappears raises a review
  item; Gold never moves it to a similar transaction.
- **Configuration errors fail the build; data problems become review items.**
- **Classification is a pure function** of the Silver transactions, account
  registry, taxonomy, rules, manual decisions, and matching policy, independent
  of import order and earlier publications.

## Considered Options

- **Bank categories as authoritative or as a fallback.** Rejected: they would
  misfile transfers and refunds without anyone noticing.
- **First matching rule in file order.** Rejected: a broad rule placed early
  silently shadows narrower ones, so conflicts never surface.
- **Most specific rule wins.** Rejected: specificity between text patterns is
  hard to define and harder to explain.
- **Rules assign a type explicitly.** Rejected: every expense rule would need a
  refund twin, and a forgotten twin misfiles a refund.
- **Rules before transfer pairing.** Rejected: a broad rule, such as one on the
  bank's "other income" label, would swallow incoming transfer legs.

## Consequences

- A positive amount matched by an expense-category rule is a refund
  automatically, so a reimbursed outlay nets against its category.
- Overlapping rules at equal priority surface as conflicts, settled with a
  priority or a narrower rule.
- Lineage names the rule or decision behind every classification, and
  classification review items are published for the CLI review workflow.
- "Manual decision" is the one term for a human ruling, whether it classifies
  a transaction or settles an import problem; "override" is not used.
- The policy, review item kinds, and synthetic scenarios are in
  [`classification.md`](../architecture/classification.md).
