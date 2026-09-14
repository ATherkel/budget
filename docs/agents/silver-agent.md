# Silver Agent Brief

## Mission

Convert Bronze source records into validated canonical transactions and
resolve duplicates without assigning household financial meaning.

## Inputs

- Bronze import runs, source records, and format failures.
- Account configuration and identity-related manual decisions.
- `architecture/silver-layer.md`, ADR-007, ADR-008, and the transaction and
  account domain documents.

## Outputs

- Canonical Silver transactions with lineage to every source record showing
  them.
- Unbooked records, balance observations, import-run results, validation
  errors, and review items, as specified in `architecture/silver-layer.md`.

## Prohibited Work

- Assigning household categories, budgets, income/expense/transfer semantics,
  coverage, or producing reports.
- Deduplicating by content alone, or by date and amount.
- Partially admitting an import run.

## Acceptance Criteria

- `Dato` parses to a date and `Beløb`/`Saldo` parse to `Decimal` for valid
  `danske-csv-v1` rows.
- `description` is the source text as delivered. The identity text is derived
  only by trimming and collapsing whitespace, as ADR-007 documents.
- Identical, overlapping, reordered, and reverse-order imports produce the
  same transactions and identifiers.
- Reprocessing the same Bronze inputs, configuration, and manual decisions
  produces the same Silver results.
- The synthetic scenarios in issue #5's resolution pass, using synthetic data
  only.
