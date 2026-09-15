# Silver Agent Brief

## Mission

Convert Bronze records into validated canonical transactions and identify
duplicates without assigning household financial meaning.

## Inputs

- Bronze records and source metadata.
- The transaction and account domain documents.

## Outputs

- Canonical Silver transactions.
- Validation errors/quarantine records with references to their source rows.
- Duplicate decisions with their deterministic matching rationale.

## Prohibited Work

- Assigning household categories, budgets, income/expense/transfer semantics,
  or producing reports.

## Acceptance Criteria

- `Dato` parses to a date and `Beløb`/`Saldo` parse to `Decimal` for valid
  current Danske rows.
- `Status` maps to `booking_status` (`Udført` → `booked`, `Slettet` →
  `cancelled`); an unmapped value is a validation error.
- Text is normalized only in a documented, non-destructive way; source text
  remains traceable to Bronze.
- Reprocessing the same Bronze inputs produces the same Silver results.
