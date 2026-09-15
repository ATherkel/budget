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

## Decision

Persist the bank-stated balance on every Silver and Gold transaction. Treat
balance-chain continuity as the reconciliation check: each transaction's
balance must equal the previous transaction's balance plus its amount, with
an account's first transaction trusted as its opening balance (there is
nothing earlier to check it against). A break in the chain, or a missing
balance value, is never silently corrected or hidden — it demotes that
account's coverage for the affected period to `partial` rather than
`complete`. Only source rows in a completed/settled booking status are
materialized as Gold transactions; the bank's own back-office reconciliation
flag (`Afstemt` in the Danske export) is not used for anything.

## Consequences

- `GoldTransaction` gains a `balance` field; Silver's canonical transaction
  gains `balance` and `source_status` fields to carry the evidence forward
  from Bronze without interpreting it.
- Coverage (`complete` / `partial` / `no_data`) becomes a real, per-account,
  per-period measure derived from this chain, instead of an implicit gap.
- A computed-only balance would have drifted silently on any missed or
  duplicated import; a snapshot-only balance would have given no way to
  detect that drift. Neither alone satisfies "trustworthy... and
  reconciliation" — checking the chain does.
- Resolves [issue #4](https://github.com/ATherkel/budget/issues/4).
