# ADR-009: Identify Transactions by Content and Occurrence, Verified by Balances

**Status:** Accepted. Amended by
[ADR-017](ADR-017-dropped-transactions.md): the `fewer-repeats` review item is
now `dropped-transactions` and also covers a transaction that was never
repeated, so the same-day case and the text-change consequence below raise it
rather than `export-disagreement`.

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
(`exported_on`, then `started_at` for exports produced on the same date), so for
exports the bank produced on different days neither the merge nor the admission
decision depends on the order the household imports them.

Exports sharing an `exported_on` are tied, and `started_at` breaks the tie by
import order, so the claim is scoped to different days on purpose. Two exports
produced on the same day usually show the same bank state and then merge
identically in either order. They differ only when the bank booked something
between the two, and `exported_on` has no resolution finer than the date to tell
them apart. The export produced earlier then looks, on arriving second, like it
is hiding a row: it is quarantined with an `export-disagreement` review item, and
any dates only it reaches stay out until the operator voids the other run and
imports it again. Identifiers are unaffected either way. This is the same
import-order failure the decision removes across days, left standing inside one
day because that is the resolution the evidence has: a finer production time is
the bank's to state, not ours to infer.

The bank-stated balance is deliberately not part of the identifier. Silver
uses it to verify its merge. A later export is admitted when both of these
hold:

- it still shows every transaction already admitted for the dates it covers;
- its end-of-day balances differ from those already admitted by exactly the
  cumulative amounts of the transactions it adds, which is *explained growth*.

Late bookings, and further bookings on an export's final date, are both
explained growth. Any unexplained difference quarantines the export admitted
later and raises an `export-disagreement` review item.

A date states an end-of-day balance only once it has a booked transaction, so
the admitted set and a new export do not always state one on the same dates. The
balances are compared where both do, which exempts nothing. A date the admitted
set states and the export covers is always stated by the export as well: the
export has to show every transaction already admitted for that date, and for a
balance-stating source every booked row carries a balance (ADR-010), so an export
that states none there is already quarantined. That leaves a date wholly new in
the export. Its transactions are all additions; they are counted at the next date
both sides state, and the export's own within-export chain ties every date it
states to the ones that are compared. Only the date the check lands on moves.

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
- Two exports the bank produced on the same day are ordered by import order
  alone. When the bank booked between them, importing the later-produced one
  first quarantines the other and withholds the dates only it reaches. The
  admitted transactions keep their identifiers, and voiding the newer run and
  re-importing it recovers the rest.
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
