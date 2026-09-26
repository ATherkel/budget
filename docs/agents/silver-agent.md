# Silver Agent Brief

## Mission

Convert Bronze source records into validated canonical transactions and
resolve duplicates without assigning household financial meaning.

## Inputs

- Bronze import runs, source records, and format failures.
- Account configuration and identity-related manual decisions.
- `architecture/silver-layer.md`, ADR-009, ADR-010, and the transaction and
  account domain documents.

## Outputs

- Canonical Silver transactions with lineage to every source record showing
  them.
- Unbooked records, balance observations, account evidence, import-run results,
  validation errors, and review items, as specified in
  `architecture/silver-layer.md`.
- `AccountEvidence.evidence_through` computed by the formula in that document,
  which is the only place the rule is stated; Gold carries it through unchanged.

## Prohibited Work

- Assigning household categories, budgets, income/expense/transfer semantics,
  coverage, or producing reports.
- Deduplicating by content alone, or by date and amount.
- Partially admitting an import run.

## Acceptance Criteria

- `Dato` parses to a date and `Beløb`/`Saldo` parse to `Decimal` for valid
  `danske-csv-v1` rows.
- `Status` maps to `booking_status` (`Udført` → `booked`, `Slettet` →
  `cancelled`); an unmapped value is a validation error.
- `description` is the identity text: the source text trimmed and with
  whitespace collapsed, as ADR-009 documents, and nothing else. Two exports
  whose texts differ only in whitespace give one transaction one `description`.
- `bank_category` and `bank_subcategory` come from the latest admitted export
  covering the transaction's date; a later export that relabels a transaction
  changes them and leaves its `transaction_id` unchanged.
- Identical, overlapping, reordered, and reverse-order imports of exports the
  bank produced on different days produce the same transactions and identifiers,
  including when an older export is imported after a newer one: runs are
  admitted in `exported_on` order. Runs sharing an `exported_on` fall back to
  import order; ADR-009 records what that can and cannot change.
- A later export that drops an admitted transaction, repeated or not,
  quarantines that run with a `dropped-transactions` review item and no
  `export-disagreement`; a *withdrawn* or *same transaction* decision for each
  dropped transaction admits it (ADR-017). A missing balance or a within-export
  chain break quarantines the run with a `balance-break` review item; an
  *accept discrepancy* decision admits it and settles that item through
  `resolved_by`.
- A late booking in a later export is admitted as explained growth: identifiers
  of existing transactions are unchanged, and that date's balances come from
  the later export.
- Reprocessing the same Bronze inputs, configuration, and manual decisions
  produces the same Silver results.
- The synthetic scenarios in issue #5's resolution pass, using synthetic data
  only. Scenarios 7 and 9 expect a `dropped-transactions` review item
  (ADR-017).
