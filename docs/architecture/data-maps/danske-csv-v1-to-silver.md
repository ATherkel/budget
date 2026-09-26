# Logical Data Map: `danske-csv-v1` → Silver

**Status:** Accepted. The map restates, column by column, what
[`silver-layer.md`](../silver-layer.md), ADR-009, ADR-010, ADR-013 and
ADR-016 decide for one source format, and decides what they leave open. Rows
and rules it decides itself are marked *Map decision*. Where the layer contract
is silent, the map is normative, and the Silver code for `danske-csv-v1`
follows it. Where it conflicts with the layer contract, an ADR or `domains/`,
those win and the map is stale.

This is the logical data map of Kimball's ETL toolkit (figure 3.1): for every
target column, where it comes from and how. It is a design document, not
configuration. Nothing reads it at run time; the Silver code for
`danske-csv-v1` is written from it and reviewed against it.

Kimball's columns are adapted to this pipeline:

- **Source** is Bronze, account configuration, or a manual decision. A source
  column is either a field of `SourceRecord.fields`, written as `Dato`, or a
  field of another record, written as `ImportRun.declared_account_id`. Every
  `SourceRecord.fields` value is a string, exactly as decoded.
- **Table type** and **SCD type** are left out. Silver holds canonical records,
  not dimensions or facts; slowly changing dimensions are Gold's, and ADR-007
  decides them there.

## Sources

| Source | Grain | Used for |
| --- | --- | --- |
| `SourceRecord` of a payload with no `FormatFailure` | one row of one payload | every per-row value |
| `FormatFailure` of a stored payload | one verdict on one payload and format | `ImportRunResult.errors` and `status`; the payload has no source records |
| `ImportRun` with outcome `stored`, not voided | one presentation of a payload | account, format, admission order |
| `ImportRun` with outcome `repeat` | one presentation of stored bytes | `AccountEvidence` only, never records |
| account configuration | one account | currency, and through it the decimal places of the minor unit (ADR-013) |
| manual decision, from the decision log ([`operations.md`](../operations.md#decisionsjsonl-the-decision-log)) | one recorded ruling | *same transaction*: `TransactionEvidence.transaction_id`, the `Transaction` grain and `ImportRunResult.status`. *withdrawn*: the `Transaction` grain and `ImportRunResult.status`. *accept discrepancy*: `ImportRunResult.status`, `balance` and `end_of_day_balance`. *void import run*: excluded by "not voided" above |

The `danske-csv-v1` fields. `bronze-layer.md` declares the header; the meanings
come from it, `domains/transaction.md`, and the sample profile in
`agents/bronze-agent.md`.

| Field | Example | Meaning |
| --- | --- | --- |
| `Dato` | `12.09.2026` | transaction date (purchase date), `DD.MM.YYYY` |
| `Kategori` | ` Mad ` | bank category, space-padded |
| `Underkategori` | ` Dagligvarer ` | bank subcategory, space-padded |
| `Tekst` | ` Café` | transaction text |
| `Beløb` | `-1.234,56` | amount, decimal comma, `.` groups thousands, negative is money out |
| `Saldo` | `2.955,00` | running balance after the row, recalculated at export time; empty on `Slettet` rows |
| `Status` | `Udført` | the bank's booking status |
| `Afstemt` | `Nej` | reconciled flag; not interpreted |

## Shared Rules

These apply wherever a column below names them.

- **Date.** *Map decision.* `Dato` is exactly `DD.MM.YYYY`: a two-digit day, a
  two-digit month and a four-digit year, separated by `.`, with no whitespace,
  naming a real calendar date. `12.09.2026` is 12 September 2026; `1.09.2026`,
  ` 12.09.2026`, `12-09-2026` and `31.02.2026` are `unparseable-date` errors on
  that record. Nothing upstream promises a readable `Dato`, so this error is a
  real path.
- **Decimal.** The value's places follow `silver-layer.md` (*Amounts*): the
  result carries exactly the decimal places of the account's currency (ADR-013's
  ISO 4217 table; two for DKK), fewer are padded, and more are rejected, never
  rounded. *Map decision:* the syntax. A value is an optional `-`, an integer
  part, and an optional `,` followed by at least one digit. The integer part is
  either digits with no `.`, or one to three digits followed by groups of `.`
  and exactly three digits, as in `1.234.567`; Danske groups thousands with
  `.`. The `.` separators are removed, the comma becomes a decimal point, and
  the result is a `Decimal`, never a float: `-45,0` becomes `Decimal("-45.00")`.
  Nothing is trimmed first. An empty `Saldo` on a booked row is a
  `missing-balance` error and never an `unparseable-decimal` one (see
  `balance`). Anything else, such as an empty `Beløb`, `1.23,00`,
  `1234.567,00`, or `-45,001` in DKK, is an `unparseable-decimal` error on that
  record.
- **Booking status.** `Status` maps as `silver-layer.md` states. *Map
  decision:* the match is exact, with no trimming or case folding.

  | `Status` | `booking_status` |
  | --- | --- |
  | `Udført` | `booked` |
  | `Slettet` | `cancelled` |
  | anything else | `unknown-status` error |

  *Map decision.* No pending value is known. The first export carrying one is
  quarantined whole with an `unknown-status` error on each such record, and its
  new dates wait. A person then decides what the value means, adds it to this
  table and to the Silver code, and runs `rebuild --from silver`
  ([`operations.md`](../operations.md)) to validate the run again.

- **Identity text.** `Tekst` with leading and trailing Unicode whitespace
  removed and internal runs collapsed to one space, including 0xA0 (ADR-009).
  It is an input to `transaction_id` and *k*, and is stored as `description`.
- **Label.** *Map decision.* `Kategori` or `Underkategori` with leading and
  trailing Unicode whitespace removed, including 0xA0, as for the identity
  text; internal whitespace is kept. A value that is empty afterwards is null.
- **Selected export.** For each account and date, the latest admitted export
  covering that date that shows every transaction kept for it (ADR-009). It
  supplies `balance`, `day_sequence`, `bank_category` and `bank_subcategory`
  (`silver-layer.md`).
- **Error codes.** *Map decision.* `silver-layer.md` (*Validation*) lists the
  errors in prose and names no `ValidationError.code`. This map names the four
  its rules raise: `unparseable-date`, `unparseable-decimal`, `unknown-status`
  and `missing-balance`. The other errors in that list, a format failure, a
  wrong field count and a balance-chain break, do not depend on this format and
  are not named here.

## Target: `Transaction`

Grain: one booked transaction. Booked records collapse by ADR-009 identity, a
*same transaction* decision adds a record to an existing transaction, and a
*withdrawn* decision removes a transaction. Only records whose `booking_status`
is `booked` contribute.

| Target column | Type | Source | Transformation |
| --- | --- | --- | --- |
| `transaction_id` | `str` | `ImportRun.declared_account_id`, `Dato`, `Beløb`, `Tekst`, account configuration | ADR-009 hash of `identity_version`, account, date, amount quantized to the minor unit of the account's currency, identity text, and `occurrence` |
| `account_id` | `str` | `ImportRun.declared_account_id` | copied |
| `transaction_date` | `date` | `Dato` | Date rule |
| `amount` | `Decimal` | `Beløb` | Decimal rule |
| `currency` | `str` | account configuration | copied; never read from the payload |
| `description` | `str` | `Tekst` | Identity text rule. Every export gives the same value, so no export is chosen; Bronze keeps the text as delivered, reachable through `TransactionEvidence` |
| `source_system` | `str` | `ImportRun.source_format` | copied: `danske-csv-v1` |
| `balance` | `Decimal \| None` | `Saldo` of the selected export | Decimal rule. An empty `Saldo` on a booked row is a `missing-balance` error and raises a `balance-break` review item (ADR-010). When *accept discrepancy* admits that run anyway, the balance is null (ADR-016) |
| `source_status` | `str` | `Status` | copied verbatim |
| `booking_status` | `Literal` | `Status` | Booking status rule; always `booked` here |
| `occurrence` | `int` | derived | *k*: 1-based count of booked rows in one export sharing account, date, quantized amount and identity text, in source order (ADR-009) |
| `day_sequence` | `int` | `SourceRecord.record_ordinal` of the selected export | 1-based order of the date's booked rows in the selected export; transactions it does not show are appended in `transaction_id` order (`silver-layer.md`) |
| `identity_version` | `str` | constant | the version of the ADR-009 rule in force |
| `bank_category` | `str \| None` | `Kategori` of the selected export | Label rule |
| `bank_subcategory` | `str \| None` | `Underkategori` of the selected export | Label rule |

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
| `transaction_id` | `str` | derived, or a *same transaction* decision | the `Transaction` this record resolves to by ADR-009 identity, or the existing one a *same transaction* decision names for it |
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
| `end_of_day_balance` | `Decimal \| None` | `Saldo` | Decimal rule, from the date's last booked row in payload order (*Map decision*). Null when *accept discrepancy* admitted an empty `Saldo` on that row (ADR-016) |
| `payload_id` | `str` | `SourceRecord.payload_id` | copied |

## Target: `ImportRunResult`

Grain: one `stored`, not voided import run, whether or not its payload has
source records.

| Target column | Type | Source | Transformation |
| --- | --- | --- | --- |
| `import_run_id` | `str` | `ImportRun.import_run_id` | copied |
| `status` | `Literal` | derived, and manual decisions | `accepted` when the run has no validation error and fails no merge check, or when every one it has belongs to a review item a manual decision has settled: *accept discrepancy* for a `balance-break`, *withdrawn* for a `fewer-repeats`, and *same transaction* for the item a bank-side text change raises (ADR-009, ADR-010). Otherwise `quarantined` |
| `covered_from` | `date \| None` | `Dato` | the earliest `Dato` among the payload's source records, booked or not; null when the payload has none, as with a `FormatFailure` or a header-only export (`silver-layer.md`) |
| `covered_to` | `date` | `ImportRun.covers_through` | copied |
| `errors` | `Sequence` | derived | every `ValidationError` listed under *Validation* in `silver-layer.md`, with the codes under Error codes where this map names one. Errors a manual decision settled stay listed (ADR-010: "the import run lists it") |
| `review_item_ids` | `Sequence` | derived | review items raised for this run, settled or not; a settled one names its decision in `ReviewItem.resolved_by` |

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
