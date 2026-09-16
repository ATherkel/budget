# Bronze Agent Brief

## Mission

Implement source ingestion and immutable provenance storage without embedding
financial business logic.

## Authority

- Read local files supplied as import inputs.
- Create raw payload, import-run, source-record, and format-failure storage as
  specified in `architecture/bronze-layer.md`.
- Record the byte checksum, declared account, source format, original filename
  (private), import timestamp, and source record ordinal.

## Prohibited Work

- Categorization, transfer detection, currency or business interpretation,
  status mapping, typing, trimming, or analytics.
- Guessing an encoding. Each source format declares its encoding and decodes
  strictly.
- Updating a previously stored raw payload in place.
- Changing downstream contracts.

## Sample CSV Profile

The current files match `danske-csv-v1` in `architecture/bronze-layer.md`:
Windows-1252, comma-delimited, quoted fields, CRLF line endings, rows oldest
first. The only values observed in `Status` are `Udført` and `Slettet`, and
`Afstemt` is always `Nej`. The single blank `Saldo` in the samples is on a
`Slettet` row, which the balance chain skips.

## Acceptance Criteria

- An import is repeatable and all raw input can be traced to an import run.
- Importing the same bytes again records a `repeat` import run and stores no
  new payload.
- The same bytes declared for a different account are refused unless the
  earlier import run is voided.
- A UTF-8 file, a byte undefined in Windows-1252, or an unexpected header
  yields a `FormatFailure` and no source records.
- The export date comes from a `…-YYYYMMDD.csv` filename suffix, or else must be
  declared; no other part of the filename is interpreted. How far the export
  reaches (`covers_through`) is declared separately. A `repeat` run records both
  dates and the run it repeats.
- A declared `covers_through` outside `[last transaction date, exported_on]` is
  refused, never clamped. The declaration is required when the payload's last
  transaction date is more than 7 days before `exported_on`, or when the payload
  has no rows; otherwise it falls back to `exported_on` and records that it did.
- Bronze has no dependency on Silver, Gold, analytics, or UI modules.
