# Bronze Layer

## Purpose

Persist source data exactly as received, and present it as source records
without interpreting it.

## Inputs

- A raw payload: CSV export bytes now, API responses later.
- The operator's declaration for the import run: the account it belongs to and
  the source format (for example `danske-csv-v1`).

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
    covers_through: date,     # the last date the export's evidence reaches
    covers_through_source: Literal["declared", "exported_on"],
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
produced the file, which is what the late-booking window is counted from. How
far the file's evidence reaches is `covers_through`, the end of the range the
operator asked the bank for.

## Rules

- **No interpretation.** Splitting a payload into source records is allowed.
  Typing, trimming, normalizing, status mapping, deduplication, and
  categorization are not.
- **Declared formats.** Each source format fixes its encoding, delimiter, and
  expected header, and decodes strictly. Encoding is never guessed. A payload
  that does not match yields a `FormatFailure` and no source records.
- **Repeat payloads.** Presenting bytes already stored for the same account
  records a new `repeat` import run and stores nothing new. It still records
  its own `exported_on` and `covers_through` and names the run it repeats: an
  account with no new activity exports the same bytes again, and that file is
  evidence that nothing happened up to its own dates. Silver reads repeat runs
  for those dates only, never for source records.
- **Account conflicts.** Presenting bytes already stored for a different
  account is `refused`, unless the earlier import run has been voided by a
  manual decision.
- **Currency.** The account's currency comes from account configuration, never
  from the payload.
- **Export date.** The export date is when the bank produced the file. It is
  read from the date suffix of a Danske-style filename (`…-YYYYMMDD.csv`);
  without one, the operator must declare it. No other part of the filename is
  interpreted.
- **Covers through.** How far an export reaches is declared by the operator as
  the end of the range they asked the bank for, because the filename cannot
  tell a year of history exported today from today's own export. Three rules
  bound the declaration, because a wrong `covers_through` is not a visible
  error: too early silently truncates the account's evidence, and too late
  silently manufactures confirmed zeros over months the export never covered.
  - **Bounded.** A declared `covers_through` must fall on or after the payload's
    last transaction date — the export demonstrably reaches at least that far —
    and on or before `exported_on`. Outside that range the import run is
    `refused`; it is never clamped or silently corrected. Reading the payload's
    last transaction date is the one thing Bronze interprets, and only to bound
    this declaration: every field is still stored and presented exactly as
    decoded.
  - **Required where the fallback would be wrong.** Falling back claims evidence
    through the day before `exported_on` (`silver-layer.md`, *Evidence Through*).
    The declaration is required, not defaulted, when that day falls in a later
    reporting period than the payload's last transaction date, and when the
    payload states no transactions at all. The first is the shape of an export
    of old history, where the fallback manufactures exactly the confirmed zeros
    this field exists to prevent; inside the last transaction's own period the
    fallback is the quiet tail of an ordinary export, which is the common case
    and must not need a declaration. The second bounds nothing on its own. A
    payload Bronze cannot decode is neither: it yields a `FormatFailure`, which
    is the more useful verdict than a missing declaration.
  - **Fallback otherwise.** In every other case an undeclared `covers_through`
    falls back to `exported_on`, and `covers_through_source` records that it
    did.

  The import summary shows both dates for the operator to check. That check is
  a second pair of eyes, never the only safeguard.

## Danske CSV Format (`danske-csv-v1`)

- Windows-1252, comma-delimited, every field double-quoted, CRLF line endings,
  and at most one final line break.
  🤖 Added by Codex (deepseek/deepseek-v4.1-flash)
- The header is exactly `Dato`, `Kategori`, `Underkategori`, `Tekst`, `Beløb`,
  `Saldo`, `Status`, `Afstemt`.
- `Dato` is exactly two day digits, two month digits and four year digits
  (`DD-MM-YYYY`), and must be a real calendar date. A one-digit day or month, a
  leading space, Unicode digits, the ISO order or trailing text is a malformed
  `Dato`, so the payload gets a format failure rather than a guessed value.
  🤖 Added by Codex (deepseek/deepseek-v4.1-flash)
- Rows are ordered oldest first by `Dato`, the transaction date (purchase
  date). A transaction the bank books days later appears at its `Dato` in later
  exports, and `Saldo` is the running balance recalculated in that order at
  export time.
- `Kategori` and `Underkategori` are space-padded. The padding is preserved
  in source records.
- The file contains no account, currency, or transaction identifier.

## Responsibilities

- provenance
- auditability
- replayability
- source-format parsing

## Ownership

Bronze Agent
