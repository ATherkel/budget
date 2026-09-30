# Bronze Layer

## Purpose

Persist source data exactly as received, and present it as source records
without interpreting it.

## Inputs

- A raw payload: CSV export bytes now, API responses later.
- The operator's declaration for the import run, an `ImportDeclaration`: the
  account it belongs to, the source format (for example `danske-csv-v1`), the
  range the export covers, and the export date when the filename does not
  carry one.

## Outputs

```python
RawPayload(
    payload_id: str,          # SHA-256 of the bytes; stored once
    byte_length: int,
    content: bytes,
)

ImportRun(
    import_run_id: str,
    payload_id: str,
    declared_account_id: str,
    source_format: str,
    original_filename: str,   # private provenance only; never in reports or logs
    exported_on: date,        # the date the bank produced the export
    exported_on_source: Literal["filename", "declared"],
    covers_from: date,        # the first date the export's evidence covers
    covers_through: date,     # the last date the export's evidence covers
    started_at: datetime,     # UTC
    outcome: Literal["stored", "repeat", "refused"],
    repeat_of: str | None,    # the import run whose payload this repeats
)

SourceRecord(
    payload_id: str,
    record_ordinal: int,      # 1-based position in the payload
    fields: Mapping[str, str],  # source field name -> value exactly as decoded
)

FormatFailure(
    payload_id: str,
    source_format: str,
    reason: str,              # e.g. undecodable byte, unexpected header
)
```

`RawPayload` is the immutable record protected by ADR-003. `SourceRecord`s
and `FormatFailure`s are derived deterministically from the payload and its
source format. They can be regenerated at any time, so a parser fix never
touches the payload.

Import-run metadata, including the export date: the date the export was
produced, read from the source filename (Danske: the `-YYYYMMDD` suffix, e.g.
`-20260914`) or declared by the operator at import. It says when the bank
produced the file, which is what the late-booking window is counted from. It
does not say what the file covers: that is the declared range from
`covers_from` through `covers_through`, the range the operator asked the bank
for.

## Rules

- **No interpretation.** Splitting a payload into source records is allowed.
  Typing, trimming, normalizing, status mapping, deduplication, and
  categorization are not.
- **Declared formats.** Each source format fixes its encoding, the delimiters
  it accepts, and expected header, and decodes strictly. Encoding is never
  guessed. A format that accepts more than one delimiter reads a payload's
  delimiter from its declared header, never by sniffing the data. A payload
  that does not match yields a `FormatFailure` and no source records.
- **Repeat payloads.** Presenting bytes already stored for the same account
  records a new `repeat` import run and stores nothing new. It still records
  its own `exported_on`, `covers_from` and `covers_through` and names the run it
  repeats: an account with no new activity exports the same bytes again, and
  that file is evidence that nothing happened over its own range. Silver reads
  repeat runs for those dates only, never for source records. The range rules
  below apply to a repeat as to any run, and a refusal takes precedence over a
  repeat.
- **Account conflicts.** Presenting bytes already stored for a different
  account is `refused`, unless the earlier import run has been voided by a
  manual decision.
- **Currency.** The account's currency comes from account configuration, never
  from the payload.
- **Export date.** The export date is when the bank produced the file. It is
  read from the date suffix of a Danske-style filename (`…-YYYYMMDD.csv`);
  without one, the operator must declare it. No other part of the filename is
  interpreted.
- **Covers from and covers through.** What an export covers is declared by the
  operator as the range they asked the bank for, from `covers_from` through
  `covers_through`, both inclusive. Both are required on every import and
  neither has a default: nothing infers them from the filename, the payload, or
  the export date, because the filename cannot tell a year of history exported
  today from today's own export, and a payload cannot tell a quiet month from a
  month it never covered. A wrong range is not a visible error: too narrow
  silently truncates the account's evidence, and too wide silently manufactures
  confirmed zeros over days the export never covered. So Bronze bounds the
  declaration:
  - `covers_from` falls on or before `covers_through`;
  - `covers_through` falls on or before `exported_on`;
  - for a payload Bronze can read, every transaction date falls within the
    range: the earliest on or after `covers_from`, and the latest on or before
    `covers_through`.

  A declaration outside these bounds makes the import run `refused`, and the
  run records the range exactly as declared; it is never clamped or silently
  corrected. Reading the payload's earliest and latest transaction dates is the
  one thing Bronze interprets, and only to bound this declaration: every field
  is still stored and presented exactly as decoded.

  A readable payload that states no transactions is bounded by the first two
  rules only, and when they hold it is `stored` (or a `repeat`): it shows the
  account was quiet over the declared range. A payload Bronze cannot decode
  yields a `FormatFailure`, still records its declared range, and is likewise
  refused only by the first two rules. The export day gets no special case:
  how far the most recent days can be trusted is for the late-booking window
  downstream to decide.

  The import summary shows the range and the export date for the operator to
  check. That check is a second pair of eyes, never the only safeguard.

## Danske CSV Format (`danske-csv-v1`)

- Windows-1252, comma- or semicolon-delimited, every field double-quoted, CRLF
  line endings, and at most one final line break.
- The bank's export dialog offers a comma, a semicolon (its default), a blank
  or a tab as the delimiter, and the two exports are otherwise byte for byte
  the same. The character after `"Dato"` in the header is the payload's
  delimiter, and every record must use it too. A payload that mixes the two,
  or is blank- or tab-delimited, gets a format failure. Because repeats compare
  exact bytes, the same export saved once with each delimiter is two payloads,
  not a `repeat`.
- The header is exactly `Dato`, `Kategori`, `Underkategori`, `Tekst`, `Beløb`,
  `Saldo`, `Status`, `Afstemt`.
  An account without bank categories instead exports exactly `Dato`, `Tekst`,
  `Beløb`, `Saldo`, `Status`, `Afstemt`, with no `Kategori` or `Underkategori`
  at all. The header names the payload's layout, and every record must have
  that layout's fields. Bronze presents only the fields a payload has and
  never adds the missing two; Silver reads their absence as null labels.
- `Dato` is exactly two day digits, two month digits and four year digits,
  separated by periods (`DD.MM.YYYY`, as in `12.09.2026`), and must be a real
  calendar date. A one-digit day or month, a leading space, Unicode digits, the
  ISO order, another separator such as `12-09-2026`, or trailing text is a
  malformed `Dato`, so the payload gets a format failure rather than a guessed
  value.
- Rows are ordered oldest first by `Dato`, the transaction date (purchase
  date). A transaction the bank books days later appears at its `Dato` in later
  exports, and `Saldo` is the running balance recalculated in that order at
  export time.
- `Kategori` and `Underkategori` are space-padded. The padding is preserved
  in source records.
  This applies where a payload has them.
- The file contains no account, currency, or transaction identifier.

## Responsibilities

- provenance
- auditability
- replayability
- source-format parsing

## Ownership

Bronze Agent
