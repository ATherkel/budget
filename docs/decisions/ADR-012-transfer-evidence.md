# ADR-012: Pair Transfers Only on Strong Evidence; Otherwise Leave Legs Unknown

**Status:** Accepted

## Context

A transfer is excluded from income and expenses, so a false transfer hides one
income and one expense of the same size. Savings still look right, and nothing
reveals the mistake. A missed transfer is less harmful: each leg stays
`unknown`, counts as unclassified, and raises a review item.

The exports carry no identifier for the other account, so the only evidence
is amount, date, and text. In the private samples:

- every same-day, opposite-amount match between the two accounts was unique,
  and the bank labelled at least one leg a transfer;
- widening the window to 3 days added matches with no transfer signal on
  either leg, and competing candidates;
- a fixed transfer amount recurs month after month;
- most bank-labelled transfers go to or come from accounts that are not
  imported.

Raised in [issue #7](https://github.com/ATherkel/budget/issues/7).

## Decision

- **A transfer needs both legs inside the reporting boundary**, which is the
  imported accounts. Money to or from any other account, even one a household
  member owns, is income or expense.
- **Candidates** are two booked transactions on different Gold accounts, with
  amounts that cancel exactly, at most 3 days apart, and neither targeted by an
  applicable manual decision.
- **Every candidate needs a rule's transfer claim on at least one leg**,
  whatever the date gap.
- **Matching runs in stages** by date gap: 0, 1, 2, then 3 days. A lone
  candidate pair is paired. Repeated transactions on each side (same account,
  date, amount, and text) are interchangeable and pair in account order. Any
  other competition leaves every competing leg `unknown`, with one review
  item.
- **A transfer claim without a pair** leaves the leg `unknown`, with a review
  item.
- **A one-sided transfer** comes only from a manual decision naming the
  counterpart Gold account, and only for a date outside that account's managed
  period.
- **Confidence is a named evidence basis in lineage**, not a score:
  `same_day`, `date_gap`, `repeated_legs`, `manual_pair`, or `one_sided`.
- `transfer_group_id` derives from the two legs' transaction identifiers.

## Considered Options

- **A numeric confidence score with a threshold.** Rejected: hard to explain
  and audit, and any threshold would be arbitrary with this little evidence.
- **Pair any unique opposite-amount match within the window.** Rejected: the
  samples contain date-gap matches with no transfer signal on either leg.
- **Pair same-day matches without a claim.** Rejected: an unrelated same-day
  coincidence would silently hide an expense and an income. Every same-day
  transfer in the samples carries a bank transfer label that a rule can claim.
- **Settle competition by nearest date or first come.** Rejected: a guess, and
  a wrong guess is silent.
- **Publish an unpaired transfer claim as a transfer.** Rejected: it would hide
  money leaving the boundary.
- **Keep a member's un-imported account inside the boundary, with one-sided
  transfers to it.** Rejected: that member's contributions would never count
  as household income, while the spending they fund would count as expenses.

## Consequences

- No transfer pairs without a claim rule. One rule on the bank's transfer label
  covers the samples.
- A transfer between banks that takes more than 3 days needs a `pair` decision.
- A transfer that loses a fee never pairs, because the amounts do not cancel.
  Each leg is classified on its own until splits exist (issue #47).
- A coincidental same-amount payment on the same day can hold a real transfer
  in review.
- Importing a new account can turn income and expenses into transfers, or a
  pair into a review item. Reports restate.
- Money moved to a savings, investment, or loan account that is not imported
  is an expense until that account is imported. Whether the savings measure
  should treat it differently is open for issue #12.
- A pair that spans a month boundary keeps each leg in its own month; income
  and expenses change in neither.
- The policy and synthetic scenarios are in
  [`classification.md`](../architecture/classification.md).
