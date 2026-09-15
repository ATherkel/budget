# ADR-009: Identify Transactions by Content and Occurrence, Verified by Balances

**Status:** Accepted

## Context

Danske CSV exports carry no transaction, account, or currency identifier, and
the household exports each account repeatedly with overlapping date ranges.
Visibly identical rows (same date, text, and amount) occur legitimately, so a
content fingerprint alone would collapse real repeated transactions. Row
position is stable within one export but changes between exports.

The export's date (`Dato`) is the transaction date, meaning the purchase date,
and the bank may book a transaction days later. A late-booked transaction
therefore appears in later exports on a date that earlier exports already
covered, and the bank recalculates every later running balance. A balance-based
identifier would change on every late booking. Manual decisions and
classifications attach to transaction identifiers, so identifiers must survive
re-imports and rebuilds.

## Decision

A booked transaction's identifier is a deterministic hash of an identity
version, the account, the transaction date, the amount, the identity text, and
an occurrence number *k*. The identity text is the source text with leading
and trailing whitespace removed and internal runs of whitespace collapsed.
*k* numbers visibly identical booked rows within one export, in source order.

When several exports of an account overlap, the number of booked transactions
for each (account, date, amount, identity text) is the highest count shown by
any single export. The merge does not depend on import order.

The bank-stated balance is deliberately not part of the identifier. Silver
uses it to verify its merge. A later export is admitted when both of these
hold:

- it still shows every transaction already admitted for the dates it covers;
- its end-of-day balances differ from those already admitted by exactly the
  cumulative amounts of the transactions it adds, which is *explained growth*.

Late bookings, and further bookings on an export's final date, are both
explained growth. Any unexplained difference quarantines the later-imported
export and raises a review item. A later export showing fewer repeated
transactions on any date also raises a review item, and the higher count is
kept.

Each date's transaction order and per-transaction balances come from one
export: the latest admitted export covering that date. It is the most
complete.

## Considered Options

- **Balance-anchored identifier** (content plus balance after): rejected
  because every late booking would re-identify all later transactions.
- **Requiring overlapping exports to agree exactly**: rejected because
  normal late bookings would quarantine most exports.
- **Row position across exports**: rejected because positions shift between
  exports.
- **Fingerprint without an occurrence number**: rejected because it merges
  legitimate repeated transactions.

## Consequences

- Re-importing identical or overlapping exports is idempotent, and manual
  decisions keep their targets.
- Per-transaction balances for a date can change when a later export adds a
  late booking. Identifiers do not.
- A bank-side text change other than whitespace creates an apparent new
  transaction. The balance check catches it as a review item, which a manual
  decision (same transaction) settles.
- Changing the identity rule requires a new identity version and a migration
  of references to transaction identifiers.
- Resolves [issue #5](https://github.com/ATherkel/budget/issues/5).
