# Bronze Agent Brief

## Mission

Implement source ingestion and immutable provenance storage without embedding
financial business logic.

## Authority

- Read local files supplied as import inputs.
- Create import-run metadata, source-file metadata, and raw-record storage.
- Record byte checksum, source name, detected encoding, import timestamp, and
  source row/order where available.

## Prohibited Work

- Categorization, transfer detection, currency/business interpretation, or
  analytics.
- Updating a previously stored source payload in place.
- Changing downstream contracts.

## Sample CSV Profile

The current files are semicolon-delimited Danske exports with quoted headers:
`Dato`, `Kategori`, `Underkategori`, `Tekst`, `Beløb`, `Saldo`, `Status`, and
`Afstemt`. They contain Danish text and decimal commas. Encoding must be
detected and recorded rather than assumed from a terminal display.

## Acceptance Criteria

- An import is repeatable and all raw input can be traced to an import run.
- Importing the same file again does not silently lose or overwrite provenance.
- Bronze has no dependency on Silver, Gold, analytics, or UI modules.
