# ADR-008: Model Category Assignment as an Allocation Fact, One Allocation per Transaction in the First Release

**Status:** Accepted

## Context

A single purchase can in reality cover several categories: nappies bought with
the groceries, or a frying pan bought with something unrelated and equally
expensive. Kimball treats "one booked transaction" and "one category allocation
of a transaction" as different grains that belong in different fact tables. The
first-release sources carry one row per booked transaction, with no line items,
so nothing upstream knows how a mixed purchase divides.

The household's reason for caring is not tidiness. Category budgets are read to
decide things. A mixed expensive purchase filed under one category makes that
category read over budget and the other read fine, when in truth both are
within budget — a wrong answer to the question the project exists to answer.
Small mixed purchases are not worth the effort, but the expensive ones are the
ones decisions are made on.

Splitting a purchase needs three things that are genuine work: a screen for
dividing a transaction by hand, a rule that the parts always add back to the
total, and an answer for which part a later refund reverses. None of them is
needed to publish trustworthy monthly totals in the first release.

[Issue #6](https://github.com/ATherkel/budget/issues/6) asked for an explicit
decision rather than an assumption either way.

## Decision

Category assignment is a fact at its own grain: one category allocation of one
booked transaction, published as `GoldCategoryAllocation`. The transaction fact
keeps the grain of one booked transaction and carries no `category_id`. Every
category and category-group measure is summed over allocations.

In the first release, a classified transaction has exactly one allocation, for
its whole amount, and no workflow exists to author a second. The contract
states that restriction as an invariant, separately from the grain, so
relaxing it later changes the invariant only.

Deferred with it: the split-entry workflow, and the rule for which allocation a
refund reverses. Until a transaction can carry several allocations, a refund
reverses the only allocation there is.

## Considered Options

- **A single `category_id` on the transaction fact, no allocations.** Rejected.
  It is less work now, by one type and one query. But every category measure
  would be written against the transaction fact, so authoring splits later
  means a contract version change, a new fact, and rewriting every consumer
  that reports by category — landing on top of the split workflow, which is
  the release that can least afford unrelated churn. It also puts the category
  on the wrong grain: the thing that changes when a household reclassifies is
  the assignment, which then has no row of its own to change.
- **Full category splits now.** Rejected for the first release. The
  split-entry workflow and refund-against-split rules are real work, and
  nothing in the first release's sources or measures needs them.
- **Decide after the classification taxonomy (issue #7) settles.** Rejected.
  Consumers are written against this contract before then, and the grain is
  what they are written against.

## Consequences

- The contract has a third fact and a fifth repository method,
  `category_allocations()`. The allocation repeats its transaction's account
  and date, so category reporting by account and month needs no join.
- Two invariants carry the weight: allocations sum exactly to their
  transaction's amount, with no rounding tolerance, and every allocation has
  the same sign as its transaction. They are testable from the first fixture,
  when they are cheap to get right.
- Household income and expenses stay transaction measures; category and
  category-group spending become allocation measures. They agree because
  allocations sum to their transactions, and they keep agreeing after splits
  exist.
- Adding splits later needs a workflow, a refund rule, and the relaxation of
  one invariant. It needs no new grain, no new fact, no interface change, and
  no change to a consumer that already reports by category.
- A mixed purchase is still reported under one category until the split
  workflow exists. Paying for an expensive unrelated item separately at the
  till remains the cheapest way to keep a category honest in the meantime.
- Per-allocation classification provenance arrives with the split workflow.
  Until then, lineage explains the transaction as a whole.
