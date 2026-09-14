# ADR-007: Identify Transactions by Content and Occurrence, Verified by Balances

**Status:** Accepted

## Context

Danske CSV exports carry no transaction, account, or currency identifier, and
the household exports each account repeatedly with overlapping date ranges.
Visibly identical rows (same date, text, and amount) occur legitimately, so a
content fingerprint alone would collapse real repeated transactions. Row
position is stable within one export but changes between exports. The
bank-stated balance distinguishes repeats well, but it is recalculated when the
bank inserts a back-dated booking, which would change every later identifier.
Manual decisions and classifications attach to transaction identifiers, so
identifiers must survive re-imports and rebuilds.

## Decision

A booked transaction's identifier is a deterministic hash of an identity
version, the account, the booking date, the amount, the identity text, and
an occurrence number *k*. The identity text is the source text with leading
and trailing whitespace removed and internal runs of whitespace collapsed.
*k* numbers visibly identical booked rows within one export, in source order.

When several exports of an account overlap, the number of booked transactions
for each (account, date, amount, identity text) is the highest count shown by
any single export. The merge does not depend on import order.

The bank-stated balance is deliberately not part of the identifier. Silver
uses it to verify its merge. End-of-day balances must agree across exports,
and they must equal the merged amounts between observed days. An export's
final date is exempt because later bookings may still arrive that day. When
exports disagree, the later-imported export is quarantined and a review item
is raised. A later export showing fewer repeated transactions on a non-final
date also raises a review item, and the higher count is kept.

Each date's transaction order and per-transaction balances come from one
export. That export is the earliest-imported admitted export in which the
date is not the final date, or else the latest admitted export.

## Considered Options

- **Balance-anchored identifier** (content plus balance after): rejected
  because a back-dated booking would re-identify every later transaction.
- **Row position across exports**: rejected because positions shift between
  exports.
- **Fingerprint without an occurrence number**: rejected because it merges
  legitimate repeated transactions.

## Consequences

- Re-importing identical or overlapping exports is idempotent, and manual
  decisions keep their targets.
- A bank-side text change other than whitespace creates an apparent new
  transaction. The balance check catches it as a review item, which a manual
  decision (same transaction) settles.
- Changing the identity rule requires a new identity version and a migration
  of references to transaction identifiers.
- Resolves [issue #5](https://github.com/ATherkel/budget/issues/5).
