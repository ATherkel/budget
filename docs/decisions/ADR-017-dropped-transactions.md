# ADR-017: Treat Every Dropped Transaction Like a Dropped Repeat

**Status:** Accepted. Amends [ADR-009](ADR-009-transaction-identity.md): its
`fewer-repeats` review item becomes `dropped-transactions` and also covers a
transaction that was never repeated.

## Context

ADR-009 admits a later export only if it still shows every transaction already
admitted for the dates it covers. It says what happens when a repeated
transaction is shown fewer times, such as two identical coffees shown once: the
run is quarantined with a `fewer-repeats` review item, the missing coffee's
amount counts as explained in the balance check, and a *withdrawn* decision
settles the item. It does not say what happens when a transaction that was never
repeated disappears, its count dropping from one to none. Issue #74 found this
while checking the `danske-csv-v1` data map against ADR-009 and ADR-010.

Two causes produce it:

- **The bank removes the transaction.** The right decision is *withdrawn*.
- **The bank changes its text.** The identity text is part of the identifier
  (ADR-009), so the export shows what reads as a new transaction in place of
  the old one. The right decision is *same transaction*.

The balances cannot tell these apart. The bank recalculates `Saldo` at export
time (ADR-010), so an export's balances agree with its own rows in both cases.
For example, `NETTO` −45,00 on 3 September is admitted, and the admitted
end-of-day balance is 955,00. A later export shows `NETTO 1234` −45,00 instead,
and also states 955,00:

- Counting the missing −45,00 as explained, as ADR-009 does for a repeat, the
  expected balance is 955,00 − (−45,00) + (−45,00) = 955,00. The balances agree.
- Not counting it, 910,00 is expected against the 955,00 stated, and the run
  raises `export-disagreement`, although the balances are right and a row is
  missing.

Had the bank removed the row instead, the export's balances from 3 September on
would be 45,00 higher, which is expected only when the missing amount is
counted.

## Decision

A later export *drops* a transaction when, on a date it covers, it shows fewer
booked transactions with that amount and identity text than are admitted,
whether two became one, two became none, or one became none. Every drop is
handled as ADR-009 handles a dropped repeat:

- The run is quarantined and raises one `dropped-transactions` review item,
  which replaces `fewer-repeats`, spanning the dates of what it drops.
- A dropped transaction's amount counts as an explained difference, so a drop
  alone never raises `export-disagreement`. That item keeps one meaning: the
  balances disagree even after every added and dropped amount is counted.
- The item is settled once each transaction it drops has a *withdrawn*
  decision, because the bank removed it, or a *same transaction* decision
  naming the record in the export that shows it under new text. The run is
  then admitted, unless another review item still holds it.

Silver never picks the decision. A dropped transaction and an added one on the
same date with the same amount look like a text change, but pairing them
without a person would deduplicate by date and amount, which the Silver brief
prohibits (`agents/silver-agent.md`).

ADR-009 argues that comparing balances only on dates both sides state exempts
nothing, because an export must show every admitted transaction for a date it
covers. An export that drops every transaction admitted for a date states no
balance there. That exempts nothing either: the drop raises its review item
whatever the balances say, and its amounts are counted at the next date both
sides state, as a wholly new date's additions are.

## Considered Options

- **Only a count of two or more dropping is `fewer-repeats`** (issue #74,
  option B). A dropped single transaction would raise `export-disagreement`,
  and *withdrawn* would have to settle that item as well. Rejected: the balance
  check would report a disagreement that is really a missing row, the same drop
  would raise a different item depending on whether the transaction had a twin,
  and `export-disagreement` would no longer mean that the balances disagree.
- **Keeping the name `fewer-repeats`.** Rejected because it misnames the
  common case, a single transaction the bank reworded.
- **Naming the item `missing-transactions`.** Rejected because `CONTEXT.md`
  avoids "missing transaction", which reads as a *Late booking*: a transaction
  an earlier export lacks, the opposite direction.

## Consequences

- ADR-009's text-change consequence now reads: a bank-side text change other
  than whitespace drops the transaction and adds an apparent new one. The row
  check catches it, not the balance check, as a `dropped-transactions` review
  item that *same transaction* settles.
- ADR-009's two exports produced on the same day: the one produced earlier,
  arriving second, drops what the bank booked between them, so it raises
  `dropped-transactions` rather than `export-disagreement`. *Withdrawn* is
  wrong there, because the other export shows the transaction. The remedy is
  still to void the other run and import it again.
- Issue #5's acceptance scenarios 7 and 9 now expect a `dropped-transactions`
  review item: scenario 7 in place of `fewer-repeats`, scenario 9 in place of
  the export disagreement. *Same transaction* still admits scenario 9 with no
  double count.
- An export imported under the wrong account drops the admitted transactions
  on the dates they share, and its balances still disagree once those are
  counted, so scenario 13 raises `export-disagreement` as before, alongside
  `dropped-transactions`.
- `silver-layer.md` (*Inputs*, *Merge verification*, `ReviewItem.kind`),
  `agents/silver-agent.md`, `CONTEXT.md` and the `danske-csv-v1` data map
  follow.
- Resolves [issue #74](https://github.com/ATherkel/budget/issues/74).
