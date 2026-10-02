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
Windows-1252, comma- or semicolon-delimited, quoted fields, CRLF line endings, rows oldest first.
Accounts without bank categories export no `Kategori` or `Underkategori`
columns. The only values observed
in `Status` are `Udført` and `Slettet`, and `Afstemt` is always `Nej`. The
single blank `Saldo` in the samples is on a `Slettet` row, which the balance
chain skips.

## Acceptance Criteria

- An import is repeatable and all raw input can be traced to an import run.
- Importing the same bytes again records a `repeat` import run and stores no
  new payload.
- The same bytes declared for a different account are refused unless the
  earlier import run is voided.
- A UTF-8 file, a byte undefined in Windows-1252, or an unexpected header
  yields a `FormatFailure` and no source records.
- The export date comes from the filename when the source format's filename
  convention carries one, or else must be declared. The only other part of the
  filename a format may read is the bank's account number. It is read only to
  check it against the account's declared `bank_account_number` before Bronze,
  and it is never stored as Bronze evidence. Each format's convention is in its
  section of `architecture/bronze-layer.md`, such as *Danske CSV Format*. The
  range the export
  covers, `covers_from` through `covers_through` (both inclusive), is declared
  separately on every import, with no default and no fallback; leaving either
  out is a usage error that records no run. A `repeat` run records its own
  export date and range, and the run it repeats.
- A declared range is refused, never clamped, when `covers_from` is after
  `covers_through`, when `covers_through` is after `exported_on`, or when a
  readable payload has a transaction dated outside the range. A readable
  payload with no transactions and a valid range is stored. An undecodable
  payload yields a `FormatFailure`, still records its declared range, and is
  refused only by the first two bounds.
- Bronze has no dependency on Silver, Gold, analytics, or UI modules.
