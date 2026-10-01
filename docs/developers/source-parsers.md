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
  `exported_on_from_filename(filename) -> date | None`, and
  `account_number_from_filename(filename) -> str | None`. The account number
  is read only so the account's declared `bank_account_number` can be checked
  before Bronze (`architecture/operations.md`, *`accounts.toml`*). The store
  never calls it, and `None` means no check applies.

Two rules the contract exists to keep:

- **Decoded fields stay as they are.** Records are `Mapping[str, str]` keyed by
  the format's own field names. Nothing is trimmed, typed, or mapped: `" Mad "`
  and `"12.09.2026"` are presented exactly as they arrived. The only value read
  rather than presented is the transaction date used for the coverage bounds
  below.
- **`first_transaction_date` and `last_transaction_date` have one job.** Both
  come from the same source date field, the earliest and the latest over every
  record whatever its order or status, and they bound the declared range from
  `covers_from` through `covers_through` (`architecture/bronze-layer.md`,
  *Covers from and covers through*). Both are `None` for a payload with no
  records. Neither is ever stored in place of the source value, and neither is
  a default for the range.

## Selecting a Parser

`budget.bronze.parsers.registry` holds one explicit map from format ID to
parser. There is no auto-detection, no entry-point discovery, and no mutable
registration API: an ID that is not in the map is refused by name before the
store reads the file.

A format's own rules may still accept a small, declared set of variants that
the payload names itself: `danske-csv-v1` accepts a comma or a semicolon, and
an eight- or six-field header, and reads both from the header. That is part of
one format, not a choice between formats, and it is never inferred from how
often a character appears.
A format's own rules may still accept a small, declared set of variants that
the payload names itself: `danske-csv-v1` accepts a comma or a semicolon, and
an eight- or six-field header, and reads both from the header. That is part of
one format, not a choice between formats, and it is never inferred from how
often a character appears.
A format ID names a **source, a representation, and a version** -
`danske-csv-v1`. Exactly one ID is declared today. `nordea-csv-v1`,
`danske-api-v1`, and `danske-csv-v2` are shapes the naming leaves room for, not
implementations. A new layout gets a new ID; an existing ID never quietly
changes meaning.

`BronzeStore(profile, parsers={...})` accepts an optional mapping from format
ID to parser. It is copied when the store opens, each parser must name the ID it
is registered under, and `None` keeps the built-in registry; passing an empty
mapping means this store accepts no format at all. The mapping exists so a test
can present the same bytes under two versions of one format and observe that
the derived cache is replaced; ordinary callers keep the declared registry, and
the one-format scope above is unchanged.

## Where The Tests Live

Test directories follow the application's responsibilities, and each module
describes observable behaviour rather than one function per implementation
helper.

- `tests/bronze/parsers/test_registry.py` - the registry: how an ID that no
  parser declares is refused.
- `tests/bronze/parsers/test_danske_csv_v1.py` - the declared rules of one
  format, observed only through `parse`, `exported_on_from_filename` and
  `account_number_from_filename`: encoding, headers, delimiters, quoting, the
  transaction-date syntax and the coverage bound it feeds, and the filename
  conventions.
- `tests/bronze/test_store.py` - the store: exact bytes, provenance, reopening,
  repeats, account conflicts, coverage and refusals, and the recording of a
  format failure, with representative `danske-csv-v1` payloads as fixtures.

The exhaustive variants of a format belong to that format's file. The store
keeps one representative payload per outcome rather than repeating the matrix,
so a rule change fails in one place instead of two.

## Adding a Format

1. Add `src/budget/bronze/parsers/<format>.py` with a parser implementing the
   contract. Keep the encoding, layout, field names, date syntax, and filename
   convention in that module: the store must not learn any of them.
2. Register it in `parsers/registry.py` under its ID.
3. Add a format-specific suite under `tests/bronze/parsers/`, following
   `tests/bronze/parsers/test_danske_csv_v1.py`.

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
