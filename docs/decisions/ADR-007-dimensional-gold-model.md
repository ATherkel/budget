# ADR-007: Model Gold Dimensionally, with Balance Snapshots and Coverage Published by Gold

**Status:** Accepted. Supersedes ADR-006 for coverage placement and the Gold interface; ADR-010 still governs quarantine.

## Context

The proposed Gold contract 0.1 exposed one flat `GoldTransaction` list through
`GoldTransactionRepository`. The first release also needs trustworthy account
balances and per-account, per-month coverage ([ADR-006](ADR-006-balance-chain-reconciliation.md)),
category rollups, and a boundary that keeps source lineage away from report
consumers. Balances are semi-additive, so they cannot simply be summed out of a
transaction list. Evaluating the balance chain needs a deterministic order of
transactions within a transaction date, which only the upstream layers know.
[Issue #6](https://github.com/ATherkel/budget/issues/6) asked which processes,
grains, facts, dimensions, keys, and balance representation form the
first-release Gold model.

## Decision

Gold is a small dimensional model with three business processes and three
facts:

- **Booked transaction fact**: one row per booked transaction on one account.
- **Category allocation fact**: one row per category allocation of a booked
  transaction, exactly one per classified transaction in the first release
  ([ADR-008](ADR-008-category-allocation-grain.md)).
- **Monthly balance snapshot fact**: one row per account per reporting month
  of the account's managed period, including months with no transactions.

All three facts share conformed **Account** and **Date** dimensions. The
allocation fact also references the **Category** dimension, which has a fixed
two-level hierarchy (category group → category). All first-release dimensions
are Type 1 (current interpretation) and are keyed by durable, household-assigned
identifiers. There are no surrogate keys and no Type 2 history.

Type 1 is chosen knowing it restates history. Two things make that acceptable
instead of lossy: a dimension key is immutable and never reused, so the past is
never made ambiguous; and every category rename, regrouping, retirement, and
direction change is recorded in
[`docs/domains/category-changes.md`](../domains/category-changes.md) when it is
made. Reproducing a report exactly as it was read is a separate need, met by
retaining the publication it was built from, which issue #8 defines. Type 2
would not have met it: it preserves what a category was called, not how a
transaction was classified, and the latter is where a household's
reinterpretations actually live.

Gold, not analytics, evaluates the balance chain. It publishes a balance check
on every transaction and coverage on every monthly balance snapshot. Analytics
reads coverage and never recomputes it.

The consumer contract is star-shaped and storage-neutral. One `GoldRepository`
returns accounts, categories, transactions, category allocations, and monthly
balance snapshots as typed records. Source lineage, such as the parent Silver transaction and how a
classification was derived, sits behind a separate `GoldLineageRepository` for
review and audit tooling only. Analytics and presentation must not depend on
it.

## Considered Options

- **Flat transaction list only (contract 0.1).** Rejected. Every consumer would
  re-derive balances, coverage, and hierarchy. Lineage identifiers would leak
  into report code, and a transaction-only interface cannot represent a known
  `no_data` month.
- **Denormalized "wide" rows with dimension attributes copied onto each
  transaction.** Rejected. It hides the model the maintainer is learning, copies
  hierarchy attributes onto every row, and still does not carry balances.
- **Coverage computed in analytics.** Rejected. It needs source-derived
  ordering and managed-period knowledge that analytics should not hold. Every
  future consumer (forecasting, API) would also have to repeat it.
- **Daily balance snapshots.** Deferred. Monthly snapshots match the reporting
  period. The bank-stated balance after each transaction still answers
  intra-month questions.

## Consequences

- The Gold contract becomes version 0.2 (still proposed) and replaces 0.1
  entirely; `docs/architecture/gold-layer.md` describes the model and is no
  longer a competing schema.
- Coverage placement moves from analytics to Gold. ADR-006's whole-period
  evidence rules remain: verified quiet months are complete, and every month
  crossed by a broken link is partial.
- ADR-006's `balance` field is renamed `balance_after`; the decision itself
  is unchanged.
- Silver must supply a stable canonical identity and a deterministic per-account
  order for booked transactions, including within a transaction date. ADR-009
  defines how, using the latest admitted export for each date.
- Introducing Type 2 dimensions, a counterparty dimension, or daily snapshots
  later is a contract version change. Type 2 in particular would mean a
  versioned dimension key on the facts, reversing the durable-key decision, so
  it is not a change of attribute policy alone. Authoring several allocations
  per transaction is not: that grain is published from the first release.
