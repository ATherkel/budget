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
- Classification rules, manual decisions, and the transfer matching policy
  in [`classification.md`](../architecture/classification.md).

## Outputs

- Account and category dimensions.
- Gold transactions that satisfy every contract invariant, including
  `account_sequence` and `balance_check`.
- Monthly balance snapshots with coverage for every month of each account's
  managed period.
- Lineage through `GoldLineageRepository`: parent Silver record,
  classification source, rule or manual decision, classification version, and
  transfer evidence.
- Classification review items through `GoldLineageRepository`.
- Synthetic contract fixtures for downstream consumers.

## Prohibited Work

- Reading raw CSV files directly.
- Exposing bank-specific columns or source identifiers through
  `GoldRepository`; they belong only in lineage.
- Using a bank category as a Gold category without a household
  classification rule.
- Guessing between competing transfer candidates.
- Making analytics or UI changes.

## Acceptance Criteria

- A source-system replacement requires no Gold schema change.
- Paired household transfers are marked `transfer` exactly when the evidence
  policy in `classification.md` accepts them.
- The synthetic scenarios in `classification.md`, used as fixtures, reproduce
  their classifications and review items exactly.
- Every Gold transaction traces back to one Silver record through lineage.
- The worked example in `gold-layer.md`, used as a fixture, reproduces its
  balance checks, snapshots, and coverage exactly.
