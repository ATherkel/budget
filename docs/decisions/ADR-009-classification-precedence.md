# ADR-009: Classify by Manual Decision, Then Transfer Pairing, Then Rules

**Status:** Proposed

## Context

Gold gives every booked transaction a type and, for income, expense, and
refund, a category. Four sources could supply it: household-authored rules,
manual decisions, the pairing of transfer legs across accounts, and the
bank's own category labels on the Danske exports.

The bank labels do not match household meaning. In the private samples they
file transfers under the bank's income and expense groups and returned goods
under income, and they leave roughly one row in ten uncategorised.

A plausible but wrong classification is worse than a visible unknown. It
silently moves money between totals, while an `unknown` counts as unclassified
and raises a review item. [Issue #7](https://github.com/ATherkel/budget/issues/7)
asked for rule precedence, the role of bank categories, and how manual
decisions are identified and reviewed.

## Decision

- **Precedence.** For each transaction, an applicable manual decision wins.
  Otherwise a transfer pair ([ADR-010](ADR-010-transfer-evidence.md)) wins.
  Otherwise the highest-priority classification rule result applies.
  Otherwise the transaction is `unknown`.
- **Rules look at one transaction only**: its account, description text,
  amount, booking date, and the bank's category labels.
- **A rule assigns a category, a transfer claim, or an adjustment with a
  reason.** For a category, the type follows from the category's direction and
  the amount's sign: an expense category gives `expense` for a negative amount
  and `refund` for a positive one, and an income category gives `income` for a
  positive amount. Any other combination is a sign mismatch, and the
  transaction stays `unknown`.
- **Priority, not file order.** Every rule has an integer priority, 0 by
  default. The highest-priority matching rules decide. If they disagree, the
  transaction stays `unknown` with a conflict review item.
- **Bank category labels are provenance.** A rule may test them. They are never
  copied into Gold and never used as a fallback.
- **Manual decisions target transaction identifiers**, which survive
  re-imports and rebuilds. A decision whose target disappears raises a review
  item, and Gold never moves it to a similar transaction.
- **Errors split by where they are visible.** A problem visible in the
  configuration alone fails the build before anything is published. A problem
  that depends on the data becomes a review item.
- **Classification is a pure function** of the Silver transactions, account
  registry, taxonomy, rules, manual decisions, and matching policy. It does not
  depend on import order or on an earlier publication.

## Considered Options

- **Bank categories as authoritative or as a fallback.** Rejected. Their
  meaning differs from the household's, and a fallback would misfile
  transfers and refunds without anyone noticing.
- **First matching rule in file order.** Rejected. A broad rule placed early
  silently shadows narrower ones, so conflicts can never surface.
- **Most specific rule wins.** Rejected. Specificity between text patterns is
  hard to define and harder to explain.
- **Rules assign a type explicitly.** Rejected. Every expense rule would need a
  twin for refunds, and a forgotten twin would misfile a refund.
- **Rules before transfer pairing.** Rejected. A broad rule, such as one on the
  bank's "other income" label, would swallow the incoming legs of transfers.

## Consequences

- A positive amount matched by an expense-category rule becomes a refund
  automatically, so a reimbursed outlay nets against its category.
- Overlapping rules at equal priority surface as conflicts. Authors settle them
  with a priority or a narrower rule.
- Lineage names the rule or decision behind every classification, and
  classification review items are published for the CLI review workflow.
- "Manual decision" is the one term for a human ruling, whether it classifies
  a transaction or settles an import problem. "Override" is not used.
- The policy, review item kinds, and synthetic scenarios are in
  [`classification.md`](../architecture/classification.md).
