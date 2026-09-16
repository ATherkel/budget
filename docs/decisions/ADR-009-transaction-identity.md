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
an occurrence number *k*. Each input has exactly one written form:

- the **amount** is quantized to the currency's minor unit, two decimals for
  DKK, so a row written `-45,0` and one written `-45,00` are the same amount;
- the **identity text** is the source text with leading and trailing whitespace
  removed and internal runs of whitespace collapsed to one space. Whitespace
  means any Unicode whitespace, including the non-breaking space (0xA0) the
  Danske export can carry;
- ***k*** numbers the booked rows sharing (account, date, amount, identity
  text) within one export, in source order. Rows are counted together when
  their *identity* texts match, so two same-day, same-amount rows written `X`
  and `X ` are two transactions with *k* 1 and 2, never one identifier.

When several exports of an account overlap, the number of booked transactions
for each (account, date, amount, identity text) is the highest count shown by
any single export. Exports are admitted in the order the bank produced them
(`exported_on`, then `started_at`), so neither the merge nor the admission
decision depends on the order the household imports them.

The bank-stated balance is deliberately not part of the identifier. Silver
uses it to verify its merge. A later export is admitted when both of these
hold:

- it still shows every transaction already admitted for the dates it covers;
- its end-of-day balances differ from those already admitted by exactly the
  cumulative amounts of the transactions it adds, which is *explained growth*.

Late bookings, and further bookings on an export's final date, are both
explained growth. Any unexplained difference quarantines the export admitted
later and raises an `export-disagreement` review item.

A later export showing fewer repeated transactions on any date quarantines that
export and raises a `fewer-repeats` review item; the higher count is kept. The
missing repeats' amounts are an explained difference, because the bank
recalculates its balances, so the same date raises no `export-disagreement` as
well. A *withdrawn* decision settles the review item: the transaction leaves
the admitted set and the export is admitted with its chain intact.

Each date's transaction order and per-transaction balances come from one
export: the latest admitted export covering that date and showing every
transaction kept for it. It is the most complete.

## Considered Options

- **Balance-anchored identifier** (content plus balance after): rejected
  because every late booking would re-identify all later transactions.
- **Requiring overlapping exports to agree exactly**: rejected because
  normal late bookings would quarantine most exports.
- **Row position across exports**: rejected because positions shift between
  exports. `domains/transaction.md` described such a fingerprint and now points
  here instead.
- **Fingerprint without an occurrence number**: rejected because it merges
  legitimate repeated transactions.
- **Admitting exports in import order** (`started_at`): rejected because an
  older export imported after a newer one cannot show what the bank booked
  after it was produced, so it would be quarantined for normal data and its
  earlier dates would be lost.
- **Admitting an export that shows fewer repeats**: rejected because the kept
  transaction has no place in that date's balances, which breaks the chain the
  merge is verified against.

## Consequences

- Re-importing identical or overlapping exports is idempotent, and manual
  decisions keep their targets, whatever order the exports arrive in.
- Silver must hold every stored export's `exported_on` before it admits any of
  them, and a rebuild replays them in that order. Importing an older export
  later re-runs the admission decisions; identifiers are unaffected.
- Per-transaction balances for a date can change when a later export adds a
  late booking. Identifiers do not.
- A bank-side text change other than whitespace creates an apparent new
  transaction. The balance check catches it as a review item, which a manual
  decision (same transaction) settles.
- Changing the identity rule requires a new identity version and a migration
  of references to transaction identifiers.
- Resolves [issue #5](https://github.com/ATherkel/budget/issues/5).
