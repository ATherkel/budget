# Logical Data Map: `danske-csv-v1` → Silver

**Status:** Draft. It restates, column by column, what
[`silver-layer.md`](../silver-layer.md), ADR-009 and ADR-010 already decide
for one source format. Where this map and those documents disagree, they win
and this map is stale.

This is the logical data map of Kimball's ETL toolkit (figure 3.1): for every
target column, where it comes from and how. It is a design document, not
configuration. Nothing reads it at run time; the Silver code for
`danske-csv-v1` is written from it and reviewed against it.

Kimball's columns are adapted to this pipeline:

- **Source** is always Bronze. A source column is either a field of
  `SourceRecord.fields`, written as `Dato`, or a field of another Bronze or
  configuration record, written as `ImportRun.declared_account_id`. Every
  `SourceRecord.fields` value is a string, exactly as decoded.
- **Table type** and **SCD type** are left out. Silver holds canonical records,
  not dimensions or facts; slowly changing dimensions are Gold's, and ADR-007
  decides them there.

## Sources

| Source | Grain | Used for |
| --- | --- | --- |
| `SourceRecord` of a payload with no `FormatFailure` | one row of one payload | every per-row value |
| `ImportRun` with outcome `stored`, not voided | one presentation of a payload | account, format, admission order |
| `ImportRun` with outcome `repeat` | one presentation of stored bytes | `AccountEvidence` only, never records |
| account configuration | one account | currency |

The `danske-csv-v1` fields, as `bronze-layer.md` declares them:

| Field | Example | Meaning |
| --- | --- | --- |
| `Dato` | `12-09-2026` | transaction date (purchase date), `DD-MM-YYYY` |
| `Kategori` | ` Mad ` | bank category, space-padded |
| `Underkategori` | ` Dagligvarer ` | bank subcategory, space-padded |
| `Tekst` | ` Café` | transaction text |
| `Beløb` | `-45,00` | amount, decimal comma, negative is money out |
| `Saldo` | `955,00` | running balance after the row, recalculated at export time; empty on `Slettet` rows |
| `Status` | `Udført` | the bank's booking status |
| `Afstemt` | `Nej` | reconciled flag; not interpreted |

## Shared Rules

These apply wherever a column below names them.

- **Date.** `Dato` is read with `%d-%m-%Y`, with the same leniency as Bronze's
  `danske_csv_v1._transaction_date` (a one-digit day or month is accepted).
  Bronze already refuses a payload with an unreadable `Dato`, so for this
  format a Silver `unparseable-date` error is a guard, not a path.
- **Decimal.** A value is an optional `-`, digits, and an optional `,` with one
  or two digits. The comma becomes a decimal point and the result is a
  `Decimal`, never a float. Nothing is trimmed first; anything else is an
  `unparseable-decimal` error on that record.
- **Booking status.** `Status` maps exactly, with no trimming or case folding:

  | `Status` | `booking_status` |
  | --- | --- |
  | `Udført` | `booked` |
  | `Slettet` | `cancelled` |
  | anything else | `unknown-status` error |

- **Identity text.** `Tekst` with leading and trailing Unicode whitespace
  removed and internal runs collapsed to one space, including 0xA0 (ADR-009).
  It is an input to `transaction_id` and *k*, never a stored column.
- **Selected export.** For each account and date, the latest admitted export
  covering that date that shows every transaction kept for it (ADR-009).

## Target: `Transaction`

Grain: one booked transaction, after duplicates collapse. Only records whose
`booking_status` is `booked` contribute.

| Target column | Type | Source | Transformation |
| --- | --- | --- | --- |
| `transaction_id` | `str` | `ImportRun.declared_account_id`, `Dato`, `Beløb`, `Tekst` | ADR-009 hash of `identity_version`, account, date, amount quantized to the currency's minor unit, identity text, and `occurrence` |
| `account_id` | `str` | `ImportRun.declared_account_id` | copied |
| `transaction_date` | `date` | `Dato` | Date rule |
| `amount` | `Decimal` | `Beløb` | Decimal rule |
| `currency` | `str` | account configuration | copied; never read from the payload |
| `description` | `str` | `Tekst` | copied exactly as delivered, padding included, from the selected export |
| `source_system` | `str` | `ImportRun.source_format` | copied: `danske-csv-v1` |
| `balance` | `Decimal` | `Saldo` of the selected export | Decimal rule. Never null for this format: an empty `Saldo` on a booked row is a `missing-balance` error and a `balance-break` review item (ADR-010) |
| `source_status` | `str` | `Status` | copied verbatim |
| `booking_status` | `Literal` | `Status` | Booking status rule; always `booked` here |
| `occurrence` | `int` | derived | *k*: 1-based count of booked rows in one export sharing account, date, quantized amount and identity text, in source order (ADR-009) |
| `day_sequence` | `int` | `SourceRecord.record_ordinal` of the selected export | 1-based order of the date's booked rows in the selected export; transactions it does not show are appended in `transaction_id` order (`silver-layer.md`) |
| `identity_version` | `str` | constant | the version of the ADR-009 rule in force |
| `bank_category` | `str \| None` | `Kategori` | trimmed; null when empty |
| `bank_subcategory` | `str \| None` | `Underkategori` | trimmed; null when empty |

Not mapped: `Afstemt`, which stays in Bronze (`silver-layer.md`, *Booking
state*).

## Target: `UnbookedRecord`

Grain: one source record whose `booking_status` is not `booked`. It is never
deduplicated.

| Target column | Type | Source | Transformation |
| --- | --- | --- | --- |
| `payload_id` | `str` | `SourceRecord.payload_id` | copied |
| `record_ordinal` | `int` | `SourceRecord.record_ordinal` | copied |
| `import_run_id` | `str` | `ImportRun.import_run_id` of the `stored` run | copied |
| `account_id` | `str` | `ImportRun.declared_account_id` | copied |
| `transaction_date` | `date` | `Dato` | Date rule |
| `amount` | `Decimal` | `Beløb` | Decimal rule |
| `source_status` | `str` | `Status` | copied verbatim |
| `booking_status` | `Literal` | `Status` | Booking status rule; `cancelled` for `Slettet` |

`Saldo` is not read: a `Slettet` row carries none, and unbooked rows are
outside the balance chain.

## Target: `TransactionEvidence`

Grain: one booked source record, from any admitted export, that shows a
transaction.

| Target column | Type | Source | Transformation |
| --- | --- | --- | --- |
| `transaction_id` | `str` | derived | the `Transaction` this record resolves to |
| `payload_id` | `str` | `SourceRecord.payload_id` | copied |
| `record_ordinal` | `int` | `SourceRecord.record_ordinal` | copied |
| `import_run_id` | `str` | `ImportRun.import_run_id` of the `stored` run | copied |

## Target: `BalanceObservation`

Grain: one account, one date, one payload, for each date on which that payload
has at least one booked row.

| Target column | Type | Source | Transformation |
| --- | --- | --- | --- |
| `account_id` | `str` | `ImportRun.declared_account_id` | copied |
| `balance_date` | `date` | `Dato` | Date rule |
| `end_of_day_balance` | `Decimal` | `Saldo` | Decimal rule, from the date's last booked row in payload order |
| `payload_id` | `str` | `SourceRecord.payload_id` | copied |

## Target: `ImportRunResult`

Grain: one admitted-or-quarantined `stored` import run.

| Target column | Type | Source | Transformation |
| --- | --- | --- | --- |
| `import_run_id` | `str` | `ImportRun.import_run_id` | copied |
| `status` | `Literal` | derived | `quarantined` if any validation error or merge check fails, else `accepted` |
| `covered_from` | `date` | `Dato` | the earliest `Dato` in the payload, booked or not |
| `covered_to` | `date` | `ImportRun.covers_through` | copied |
| `errors` | `Sequence` | derived | every `ValidationError` raised by the rules above |
| `review_item_ids` | `Sequence` | derived | review items raised for this run |

`AccountEvidence` reads only `ImportRun` fields, so it is format-independent
and the formula in `silver-layer.md` is its whole map.

## Open Questions

Open questions about this map live only as GitHub issues whose body names this
file:
[the open ones](https://github.com/ATherkel/budget/issues?q=is%3Aissue+is%3Aopen+%22danske-csv-v1-to-silver.md%22).
Where a question is open, the rows above follow the issue's proposal. Each
issue lists the rows its answer changes; update them when you close it.

To raise a new question, open an issue that names
`docs/architecture/data-maps/danske-csv-v1-to-silver.md`, so the link above
finds it.
