# ADR-016: A Missing Balance Admitted by Accept Discrepancy Stays Null

**Status:** Accepted. Amends the first consequence of
[ADR-010](ADR-010-quarantine-inconsistent-exports.md).

## Context

ADR-010 quarantines a balance-stating export when a booked row lacks a
balance, and its *accept discrepancy* decision admits such a run with the break
recorded. Its consequences also say:

> For balance-stating sources, Silver and Gold never hold a booked transaction
> with a null balance.

Both cannot hold. Silver takes a date's balances from the latest admitted
export covering that date (ADR-009). Once an accepted run with a blank `Saldo`
is that export, the transaction has no balance to copy. Issue #61 found this
while drafting the `danske-csv-v1` logical data map.

For example, the export of 1 October shows a booked row on 12 September with an
empty `Saldo`. Silver quarantines the run and raises a `balance-break` review
item. The operator judges the blank real in the source and records *accept
discrepancy*. The run is now the latest admitted export covering 12 September,
so it supplies that transaction's `balance` and, if the row is the date's last
booked row, the date's `end_of_day_balance`.

Two other answers were rejected:

- **Skip the blank when selecting.** A date's balances would come from the
  latest admitted export that states one on every booked row. That departs
  from ADR-009's one selected export per date, and no earlier export may
  exist.
- **Accept only chain breaks.** A missing balance would stay quarantined. If
  the bank keeps writing the blank, every later export covering that date is
  quarantined too, which is the "no way back" case ADR-010 exists to prevent.

## Decision

When *accept discrepancy* admits an import run in which a booked row states no
balance, the value that row supplies is null:

- the transaction's `balance`, while that run is the selected export for its
  date;
- the date's `BalanceObservation.end_of_day_balance` for that payload, when the
  row is the date's last booked row.

Nothing fills the blank. No balance is computed from neighbouring rows or
copied from another export. Selection is unchanged: a later admitted export
that states the balance becomes the selected export and supplies it.

A null `end_of_day_balance` states no balance, so merge verification does not
compare that date; it still compares every other date both exports state
(`silver-layer.md`, *Merge verification*).

Gold needs no new rule. A null `balance_after` already has `balance_check`
`missing_balance`, and neither link beside it is verified, so every period
those links span is `partial` (`gold-layer.md`). That is what ADR-010 already
promises for an accepted discrepancy.

## Consequences

- ADR-010's first consequence now reads: for balance-stating sources, Silver
  and Gold hold a booked transaction with a null balance only when *accept
  discrepancy* admitted the export that supplies it.
- A missing balance without that decision still quarantines the whole export.
- `silver-layer.md`: `balance` and `BalanceObservation.end_of_day_balance` may
  be null in this case, and `end_of_day_balance` becomes `Decimal | None`.
- `gold-contract.md`: `balance_after` may be null in this case. Its type is
  already nullable, so no consumer changes.
- Resolves [issue #61](https://github.com/ATherkel/budget/issues/61).
