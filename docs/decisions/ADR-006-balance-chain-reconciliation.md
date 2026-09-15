# ADR-006: Reconcile Account Balances via Bank-Stated Balance Chains

**Status:** Accepted. Partly superseded by
[ADR-010](ADR-010-quarantine-inconsistent-exports.md): for balance-stating
sources, a missing balance or a within-export chain break quarantines the
export.

## Context

`GoldTransaction` had no balance representation at all, yet "trustworthy
account balances and reconciliation" is a stated requirement for the first
release. The source CSV exports already carry a bank-stated balance on every
row — not a separate periodic statement. Three shapes were considered: trust
only a periodic bank-stated snapshot, compute the balance purely by summing
transaction amounts, or reconcile both.

Two properties of the evidence shape the check. Dates alone do not order an
account's transactions: the sample Lønkonto export has 131 days with several
rows, up to 15 on one day, and the chain holds only in the bank's own row
order. And a chain proves only that nothing is missing *between* two known
rows; it says nothing about the days after the last imported row.

## Decision

Persist the bank-stated balance on every Silver and Gold transaction, exactly
as stated. Order each account's transactions by `(transaction_date,
day_sequence)`; Silver assigns `day_sequence` from the bank's row order and
merges overlapping exports into one order.

Balance-chain continuity is the reconciliation check, and analytics evaluates
it. A link between two consecutive transactions is verified when the later
balance equals the earlier balance plus the later amount. An account's first
transaction is trusted as its opening balance, since there is nothing earlier
to check it against.

Coverage is judged over the whole reporting period, not only the rows inside
it. An account's evidence runs from its first transaction to the day before
its latest export date; the export date is read from the export's filename or
declared at import, and the export day itself may still be booking. A period
is `complete` only when that evidence starts before the period, reaches its
end, and every link overlapping the period is verified. A period with no
transactions inside verified evidence is a confirmed zero. A broken link makes
every period it spans `partial`. Gold exposes each account's `coverage_start`
and `evidence_through` through `list_accounts()`, so an account with no
transactions in a period is still reported.

A break in the chain, or a missing balance value, is never silently corrected
or hidden. Silver maps each source's status to `booking_status` (`booked`,
`pending`, or `cancelled`), and only `booked` rows are materialized as Gold
transactions or take part in the chain. The bank's own back-office
reconciliation flag (`Afstemt` in the Danske export) is not used for anything.

## Consequences

- `GoldTransaction` gains `balance` and `day_sequence`; Silver's canonical
  transaction gains `balance`, `day_sequence`, and `booking_status`. Bronze
  records each import run's export date.
- A new connector adds only a Silver status mapping; Gold never sees a bank's
  status vocabulary.
- The Gold contract gains `GoldAccount`, `list_accounts()`, and
  `boundary_transactions()`.
- Coverage (`complete` / `partial` / `no_data`) becomes a real, per-account,
  per-period measure derived from this evidence, instead of an implicit gap.
- The chain cannot detect missing rows whose amounts sum to zero between two
  linked rows, and the export date is trusted as the extent of an export.
- A computed-only balance would have drifted silently on any missed or
  duplicated import; a snapshot-only balance would have given no way to
  detect that drift. Neither alone satisfies "trustworthy... and
  reconciliation" — checking the chain does.
- Resolves [issue #4](https://github.com/ATherkel/budget/issues/4).
