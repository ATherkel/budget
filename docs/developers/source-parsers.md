# Source Parsers

Bronze splits one raw payload into source records. Which rules apply is a
property of the *declared* source format, so the store asks a parser to do it
and never guesses from a bank, an account, a filename, or a header.

## The Contract

`budget.bronze.parsers.base` declares it:

- `ParserResult` is one payload's `records`, its `last_transaction_date`, and an
  optional `failure_reason`. `ParserResult.matched(...)` and
  `ParserResult.failed(...)` are convenience constructors for the two cases a
  parser reports. A parser must not report records and a failure reason
  together; the dataclass is a plain frozen record that does not validate that,
  so the obligation rests on the parser. A reason describes the payload as a
  whole and repeats neither source content nor the file's private name, which
  keeps it safe to show or log.
- `SourceParser` is `source_format`, `parse(content: bytes) -> ParserResult`,
  and `exported_on_from_filename(filename) -> date | None`.

Two rules the contract exists to keep:

- **Decoded fields stay as they are.** Records are `Mapping[str, str]` keyed by
  the format's own field names. Nothing is trimmed, typed, or mapped: `" Mad "`
  and `"12-09-2026"` are presented exactly as they arrived. The only value read
  rather than presented is the transaction date used for the coverage bound
  below.
- **`last_transaction_date` has one job.** It bounds a declared
  `covers_through` (`architecture/bronze-layer.md`, *Covers through*). It is
  never stored in place of the source value.

## Selecting a Parser

`budget.bronze.parsers.registry` holds one explicit map from format ID to
parser. There is no auto-detection, no entry-point discovery, and no mutable
registration API: an ID that is not in the map is refused by name before the
store reads the file.

A format ID names a **source, a representation, and a version** -
`danske-csv-v1`. Exactly one ID is declared today. `nordea-csv-v1`,
`danske-api-v1`, and `danske-csv-v2` are shapes the naming leaves room for, not
implementations. A new layout gets a new ID; an existing ID never quietly
changes meaning.

## Adding a Format

1. Add `src/budget/bronze/parsers/<format>.py` with a parser implementing the
   contract. Keep the encoding, layout, field names, date syntax, and filename
   convention in that module: the store must not learn any of them.
2. Register it in `parsers/registry.py` under its ID.
3. Add a test at the registry seam; `tests/test_source_parsers.py` shows the
   shape.

## Limits These Decisions Do Not Solve

- **Richer records.** `SourceRecord.fields` is `Mapping[str, str]`. A payload
  whose records are nested - a JSON API response, for example - cannot be
  presented faithfully through it yet. That needs a record-contract decision
  before an API format is implemented.
- **Derived cache scoping.** Format failures are keyed by
  `(payload_id, source_format)`, but source records are keyed by
  `(payload_id, record_ordinal)`. That is unambiguous while one payload has one
  owner and one declared format. If identical bytes can honestly be read as two
  formats, the derived-record cache has to be scoped by `source_format` as well
  before the second format is accepted input.
- **Acquisition is not parsing.** Authentication, pagination, retries, and
  consent belong to whatever fetches the bytes; a parser only ever sees exact
  bytes.
