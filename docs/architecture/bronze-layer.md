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
    started_at: datetime,     # UTC
    outcome: Literal["stored", "repeat", "refused"],
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

## Rules

- **No interpretation.** Splitting a payload into source records is allowed.
  Typing, trimming, normalizing, status mapping, deduplication, and
  categorization are not.
- **Declared formats.** Each source format fixes its encoding, delimiter, and
  expected header, and decodes strictly. Encoding is never guessed. A payload
  that does not match yields a `FormatFailure` and no source records.
- **Repeat payloads.** Presenting bytes already stored for the same account
  records a new `repeat` import run and stores nothing new.
- **Account conflicts.** Presenting bytes already stored for a different
  account is `refused`, unless the earlier import run has been voided by a
  manual decision.
- **Currency.** The account's currency comes from account configuration, never
  from the payload.

## Danske CSV Format (`danske-csv-v1`)

- Windows-1252, comma-delimited, every field double-quoted, CRLF line endings,
  and no final line break.
- The header is exactly `Dato`, `Kategori`, `Underkategori`, `Tekst`, `Beløb`,
  `Saldo`, `Status`, `Afstemt`.
- Rows are ordered oldest first.
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
