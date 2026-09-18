# Gold Agent Brief

## Mission

Materialize the household's dimensional Gold model from Silver transactions
according to the versioned [Gold contract](../architecture/gold-contract.md)
and the model in [gold-layer.md](../architecture/gold-layer.md).

## Inputs

- Silver canonical transactions, with their stable identity and deterministic
  per-account order.
- Household account registry.
- Household category taxonomy (category groups and categories).
- Versioned categorization rules and auditable manual overrides.

## Outputs

- Account and category dimensions.
- Gold transactions that satisfy every contract invariant, including
  `account_sequence` and `balance_check`.
- One category allocation per classified transaction, for its whole amount,
  with the allocation sum and sign invariants enforced.
- Monthly balance snapshots with coverage for every month of each account's
  managed period.
- Lineage through `GoldLineageRepository`: parent Silver record,
  classification provenance, rule/manual version, and transfer-match evidence.
- Synthetic contract fixtures for downstream consumers.

## Prohibited Work

- Reading raw CSV files directly.
- Exposing bank-specific columns or source identifiers through
  `GoldRepository`; they belong only in lineage.
- Making analytics or UI changes.

## Acceptance Criteria

- A source-system replacement requires no Gold schema change.
- Paired household transfers are marked `transfer` when matching evidence
  meets the documented confidence policy.
- Every Gold transaction traces back to one Silver record through lineage.
- The worked example in `gold-layer.md`, used as a fixture, reproduces its
  balance checks, snapshots, and coverage exactly.
