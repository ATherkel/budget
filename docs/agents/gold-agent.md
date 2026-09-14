# Gold Agent Brief

## Mission

Materialize household business facts from Silver transactions according to the
versioned [Gold contract](../architecture/gold-contract.md).

## Inputs

- Silver canonical transactions.
- Household account registry.
- Versioned categorization rules and auditable manual overrides.

## Outputs

- Gold transactions that satisfy every contract invariant.
- Classification provenance, rule/manual version, and transfer-match evidence.
- Synthetic contract fixtures for downstream consumers.

## Prohibited Work

- Reading raw CSV files directly.
- Exposing bank-specific columns or source identifiers to Gold consumers.
- Making analytics or UI changes.

## Acceptance Criteria

- A source-system replacement requires no Gold schema change.
- Paired household transfers are marked `transfer` when matching evidence
  meets the documented confidence policy.
- Every Gold record traces back to one Silver record.
