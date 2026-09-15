# ADR-010: Pair Transfers Only on Strong Evidence; Otherwise Leave Legs Unknown

**Status:** Proposed

## Context

A transfer is excluded from income and expenses. A false transfer therefore
hides one income and one expense of the same size: savings look right, and
nothing reveals the mistake. A missed transfer that stays `unknown` is less
harmful, because each leg is unclassified and raises a review item that a
person sees.

The exports carry no identifier for the other account, so the only evidence
is amount, date, and text. In the private samples:

- every same-day, opposite-amount match between the two accounts was unique;
- in every such match, the bank labelled at least one leg a transfer;
- widening the window to 3 days added matches with no transfer signal on
  either leg, as well as competing candidates;
- a fixed transfer amount recurs month after month;
- most bank-labelled transfers go to or come from accounts that are not
  imported.

[Issue #7](https://github.com/ATherkel/budget/issues/7) asked for transfer
confidence and evidence, ambiguous matches, and unmatched and cross-period
legs.

## Decision

- **A transfer needs both legs inside the reporting boundary.** An account the
  household does not import is outside the boundary, even when a household
  member owns it. Money to or from it is income or expense.
- **Candidates** are two booked transactions on different Gold accounts, with
  amounts that cancel exactly, at most 3 days apart, and neither targeted by a
  manual decision.
- **Same-day candidates need nothing more.** Candidates on different dates also
  need a transfer claim from a classification rule on at least one leg.
- **Matching runs in stages** by date gap: 0, 1, 2, then 3 days. A single
  candidate pair is paired. Repeated transactions on each side (same account,
  date, amount, and text) are interchangeable and are paired in account order.
  Any other competition leaves every competing leg `unknown`, with one review
  item. Gold does not guess.
- **A transfer claim without a pair** leaves the leg `unknown`, with a review
  item.
- **A one-sided transfer** comes only from a manual decision. The decision names
  the counterpart Gold account, and the booking date must fall outside that
  account's managed period.
- **Confidence is a named evidence basis in lineage**, not a score:
  `same_day`, `date_gap`, `repeated_legs`, `manual_pair`, or `one_sided`.
- `transfer_group_id` derives from the two legs' transaction identifiers.

## Considered Options

- **A numeric confidence score with a threshold.** Rejected. It is hard to
  explain and audit, and any threshold would be arbitrary with this little
  evidence.
- **Pair any unique opposite-amount match within the window.** Rejected. The
  samples contain date-gap matches with no transfer signal on either leg.
- **Settle competition by nearest date or first come.** Rejected. It is a guess,
  and a wrong guess is silent.
- **Publish an unpaired transfer claim as a transfer.** Rejected. It would hide
  money leaving the boundary.
- **Keep a member's un-imported account inside the boundary, with one-sided
  transfers to it.** Rejected. That member's contributions would never count as
  household income, while the spending they fund would count as expenses.

## Consequences

- A transfer between banks that takes more than 3 days needs a `pair` decision.
- A coincidental payment of the same amount on the same day can hold a real
  transfer in review.
- Importing a new account can turn income and expenses into transfers, or
  turn a pair into a review item. Reports restate.
- Money moved to a savings, investment, or loan account that is not imported
  counts as an expense. Importing the account turns it into a transfer. Whether
  the savings measure should treat it differently is open for issue #12.
- A pair that spans a month boundary keeps each leg in its own month. Household
  income and expenses change in neither month.
- The policy and synthetic scenarios are in
  [`classification.md`](../architecture/classification.md).
