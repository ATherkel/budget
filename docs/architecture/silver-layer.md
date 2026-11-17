---
type: architecture
---
# Silver Layer

## Summary

- Silver converts source records into validated, source-neutral canonical
  records, and resolves which source records show the same booked transaction.
- An import run is admitted whole or quarantined whole; overlapping exports
  merge only when their balances explain the difference.
- It hands Gold canonical transactions with a stable identity and order,
  [evidence ranges](#evidence-ranges), and [build provenance](#build-provenance).
- Decisions: [ADR-009](../decisions/ADR-009-transaction-identity.md) (identity),
  ADR-010 (balances), ADR-016 to ADR-018 (discrepancies and drops), ADR-020
  (provenance).

## Inputs

- Bronze import runs with outcome `stored` that have not been voided, with
  their source records or format failures.
- Account configuration: each account's currency.
- Manual decisions that affect identity, from the decision log
  ([`operations.md`](operations.md#decisionsjsonl-the-decision-log)).
  - *void import run*
  - *same transaction*: a source record shows an existing transaction, such as
    one whose text the bank changed.
  - *withdrawn*: the bank removed a transaction. With *same transaction*, it is
    one of the two decisions that settle a transaction a later export dropped
    (ADR-017).
  - *accept discrepancy*: an import run's balance break is real in the source
    and is admitted with the break recorded (ADR-010). A booked row it admits
    without a balance keeps a null balance (ADR-016).

## Canonical Transaction

One record per booked transaction, after duplicates are collapsed.

```python
Transaction(
    transaction_id: str,        # ADR-009 identity hash
    account_id: str,
    transaction_date: date,     # the source's transaction date (Danske: purchase date)
    amount: Decimal,
    currency: str,              # from account configuration
    description: str,           # ADR-009 identity text
    source_system: str,         # source format, e.g. "danske-csv-v1"
    balance: Decimal | None,
    source_status: str,
    booking_status: Literal["booked", "pending", "cancelled"],
    occurrence: int,            # k among visibly identical transactions
    day_sequence: int,          # order within transaction_date
    identity_version: str,
    bank_category: str | None,  # provenance only; trimmed, null when empty
    bank_subcategory: str | None,
)
```

- `balance` is the bank-stated balance right after the transaction, null only
  for a source that states none (ADR-010) or a row without one in an export
  *accept discrepancy* admitted (ADR-016).
- `source_status` is the source's status value, verbatim.
- `description` is ADR-009's identity text: the source text trimmed, with
  internal whitespace runs collapsed to one space, so every export gives a
  transaction the same text. Bronze keeps the delivered text, reachable through
  `TransactionEvidence`.
- `bank_category` and `bank_subcategory` are the source's labels with leading
  and trailing Unicode whitespace (0xA0 included) removed and internal
  whitespace kept; empty means null.

For each date, `balance`, `day_sequence` and the labels come from the
**selected export**: the latest admitted one covering that date that shows
every transaction kept for it (ADR-009). They can change with a later export;
`transaction_id` never does.

Within a date, `day_sequence` keeps the selected export's row order, never
sorted by amount or text. A kept transaction that export does not show is
appended after its rows in `transaction_id` order, never numbered from its
occurrence *k*, which two appended transactions can share:
`(account_id, transaction_date, day_sequence)` must stay unique for Gold's
`account_sequence` (Gold invariant 10). The rules below make this a guard, not
a path.

## Evidence Ranges

Silver computes the days each account's admitted exports are known to cover
and passes them on as `AccountEvidence`, one row per stretch of consecutive
covered days. This is the one definition; Gold reads the ranges rather than
deriving them.

```text
evidence(account) = the union, over that account's admitted import runs, of
    [covers_from, covers_through]
written as maximal stretches of consecutive days
```

Each run's range is the one the operator declared (`bronze-layer.md`, *Covers
from and covers through*), never adjusted. How far recent days can be trusted
is the late-booking window's job
([`presentation-layer.md`](presentation-layer.md#data-trust-display)).

Overlapping or touching ranges form one stretch (1–15 and 16–31 March give
1–31 March). An undeclared day is a gap, never covered (January–March and
May–June leave April a gap). The union depends only on the declared ranges,
never on import order.

`repeat` runs of an admitted payload count, with their own dates but no
records, which is how a quiet account extends its evidence. An account with no
admitted run has no `AccountEvidence`, and its `coverage_start` and
`evidence_through` are null.

Each counted run is also passed on as an `EvidenceExport`, so Gold settles
[late bookings](gold-layer.md#late-bookings-settled) without reading Bronze;
`ImportRunResult` cannot serve, as it exists only for `stored` runs.

## Other Outputs

```python
TransactionEvidence(            # lineage: every source record showing a transaction
    transaction_id: str,
    payload_id: str,
    record_ordinal: int,
    import_run_id: str,
)

UnbookedRecord(                 # retained provenance; never a transaction
    payload_id: str,
    record_ordinal: int,
    import_run_id: str,
    account_id: str,
    transaction_date: date,
    amount: Decimal,
    source_status: str,
    booking_status: Literal["booked", "pending", "cancelled"],
)

BalanceObservation(             # bank-stated end-of-day balance per export
    account_id: str,
    balance_date: date,
    end_of_day_balance: Decimal | None,  # null only as for balance (ADR-016)
    payload_id: str,
)

AccountEvidence(                # one evidence range; see Evidence Ranges
    account_id: str,
    covers_from: date,          # first day of the range, inclusive
    covers_through: date,       # last day of the range, inclusive
)

EvidenceExport(                 # one import run counted in an evidence range
    import_run_id: str,         # the counted run (Bronze)
    account_id: str,            # the account the run declared (Bronze)
    exported_on: date,          # the run's export date (Bronze)
    covers_from: date,          # the run's declared range, inclusive (Bronze)
    covers_through: date,
)

ImportRunResult(
    import_run_id: str,
    account_id: str,            # the account the run declared (Bronze); never empty
    status: Literal["accepted", "quarantined"],
    covered_from: date,         # the import run's covers_from (Bronze)
    covered_to: date,           # the import run's covers_through (Bronze)
    errors: Sequence[ValidationError],
    review_item_ids: Sequence[str],
)

ValidationError(
    payload_id: str,
    record_ordinal: int | None, # None for payload-level problems
    code: str,
    message: str,
)

ReviewItem(
    review_item_id: str,        # deterministic
    kind: Literal["export-disagreement", "dropped-transaction", "balance-break"],
    account_id: str,
    date_from: date,
    date_to: date,
    payload_ids: Sequence[str],
    resolved_by: str | None,    # manual decision id
    transaction_id: str | None, # the dropped transaction, for `dropped-transaction`;
                                # None for every other kind (ADR-018)
)
```

`ImportRunResult.account_id`, `covered_from` and `covered_to` are the run's
declared account and range, copied from Bronze, so a quarantined run is named
from Silver alone. The range describes the file, never the admitted dates:
Bronze refused any run with records outside it, and a run with no records (a
quiet header-only export, or a `FormatFailure`) still has it.

## Build Provenance

Silver owns the stored identity of a build and its atomicity. The accepted
completed boundary has these types:

| Field | Type | Meaning |
| --- | --- | --- |
| `SilverBuild.result` | `SilverResult` | The complete Silver result being stored. |
| `SilverBuild.currencies` | `Mapping[str, str]` | Full account-to-currency snapshot needed to decode every persisted amount. |
| `SilverBuild.provenance` | `SilverProvenance \| None` | Completed identity, or explicit unknown when a direct replacement supplies none. |
| `SilverImportRun` | `import_run_id: str; payload_id: str; account_id: str` | Immutable Bronze reference for one stored or repeated run. |
| `SilverProvenance.fingerprint_scheme` | `str` | Versioned identifier for the canonical fingerprint serialization. |
| `SilverProvenance.result_fingerprint` | `str` | SHA-256 of the complete result and consumed-currency projection. |
| `SilverProvenance.import_runs` | `frozenset[SilverImportRun]` | Every run Silver interpreted; mutable or descriptive run metadata is not copied. |
| `SilverProvenance.currencies` | `Mapping[str, str]` | Currencies of exactly the run accounts, including a run account later voided. |
| `SilverProvenance.decisions` | `Sequence[SilverDecision]` | Effective typed Silver decisions consumed by the build. |
| `SilverProvenance.decision_log_position` | `int` | Position in the Decision log consumed. |
| `SilverProvenance.decision_log_prefix_sha256` | `str` | SHA-256 of exactly the consumed log prefix. |
| `SilverProvenance.code_version` | `str \| None` | Silver producer commit when the profile records one. |
| `SilverProvenance.identity_version` | `str` | Silver identity-contract version. |
| `SilverProvenance.bronze_parser_provenance` | `Literal["unknown"]` | No Bronze parser identity is established. |

The fingerprint covers every public result family and the consumed-currency
projection. Incidental record order and decimal scale do not affect it;
duplicates and meaningful sequence fields do.

One transaction replaces `SilverBuild.result`, `SilverBuild.currencies`, the
provenance value, and a completion marker. Readers take one SQLite snapshot,
so they cannot combine rows from different builds.

`SilverStore` is the seam to `silver.db`: `replace(result, currencies=...)`
writes one complete result, leaving the previous one readable on failure, and
`read()` returns it with `Decimal` money in build order. A pipeline command
calls `rebuild_silver(profile, inputs=SilverBuildInputs(...))`, which holds the
writer lock, runs the pure `budget.silver.build` and replaces the result; a
command already holding the lock passes its `WriterLock` instead.

No completion marker means never built. A replacement without provenance is
complete but explicitly unknown. A migrated pre-provenance result is cleared,
since its inputs and producer cannot be inferred.

`rebuild --from bronze` reparses with the installed parser, so a parser change
can give a new result from the same runs; until Bronze records parser
identity, Silver never claims today's parser produced historical records.
Gold's use of provenance is [Gold acceptance](publications.md#gold-acceptance).

## Rules

**Amounts**
- Every `amount`, `balance` and `end_of_day_balance` carries exactly the
  currency's decimal places: two for DKK. The places come from the ISO 4217
  table keyed by the account's configured currency (ADR-013). A source value
  with fewer places is padded, so `-45,0` and `-45,00` both become
  `Decimal("-45.00")`. Every export that shows a transaction therefore gives it
  the same `amount`, in the same written form, and that is the value ADR-009
  hashes.
- A source value with more decimal places than its currency allows is an
  unparseable decimal. Silver never rounds it.

**Duplicates**
- Silver never collapses records by content alone, or by date and amount.
  Two records are one transaction only by canonical identity (ADR-009) or a
  person's *same transaction* decision.

**Booking state**
- Each source format maps its status values to `booking_status`: `booked`,
  `pending`, or `cancelled`. For `danske-csv-v1`, `Udført` is `booked`,
  `Venter` is `pending` and `Slettet` is `cancelled`. Only booked rows enter
  the canonical transaction output; pending and cancelled rows remain
  `UnbookedRecord` provenance.
- An unknown status value is a validation error. Gold never sees a source
  status vocabulary.
- `Afstemt` is retained in Bronze only and is not interpreted.

**Validation**
- An import run is admitted whole or quarantined whole, with every error
  listed against its source record. Nothing is partially imported.
- Errors include:
  - a format failure;
  - a wrong field count;
  - an unparseable date or decimal, including a decimal with more places than
    its currency allows;
  - an unknown status;
  - a booked row without a balance, or a balance-chain break within the
    export (ADR-010);
  - an export without bank labels that would replace labelled transactions
    (*Label layout*).
- A booked row without a balance, or a chain break within the export, also
  raises a `balance-break` review item for the run: the item an *accept
  discrepancy* decision answers through `resolved_by` (ADR-010), so the
  operator's work list shows the way back.
- `ValidationError.code` names the error. The codes that do not depend on the
  source format are `format-failure` and `label-layout-regressed`
  (payload-level, so `record_ordinal` is null), `wrong-field-count` (the
  record's fields are not exactly one of the format's headers) and
  `balance-chain-break`. Each source format's data map names the rest.

**Label layout**
- Each source format's data map says which of its layouts carry bank labels.
- A run with no record in a labelled layout gets `label-layout-regressed` when
  a labelled admitted export is the selected export for a date the run covers
  and has transactions on, since admitting it would null those labels. Dates
  without transactions, and runs without records, never trigger it. The
  message names each conflicting `payload_id` with the first and last date of
  labels at stake.
- Runs are judged in admission order (*Merge verification*), so an older
  unlabelled export is admitted and a newer labelled one still supplies labels.
  The rule only keeps labels Silver has: if the bank drops an account's labels,
  an export starting after the labelled dates is admitted.
- No decision settles it. The likely cause is an export declared for the wrong
  account; *void import run* on whichever one it is removes the conflict.

**Identity and merging**
- Per ADR-009: content plus occurrence identity, and the highest count per
  export when exports overlap.
- `transaction_id` is the lowercase hexadecimal SHA-256 of the UTF-8 encoding
  of the compact JSON array `[identity_version, account_id, transaction_date,
  amount, description, occurrence]`:
  - `transaction_date` is written in ISO 8601;
  - `amount` is written with exactly the currency's decimal places, for
    example `"-45.00"`;
  - `occurrence` is an integer;
  - `identity_version` is `"1"`.

  The array's element boundaries keep any two different inputs from
  serializing alike. `account_id` is an input, so identical purchases on two
  accounts get two identifiers.
- `review_item_id` is the same hash over `[kind, import_run_id]`, the run that
  raised the item. A `dropped-transaction` item appends its `transaction_id`,
  hashing `[kind, import_run_id, transaction_id]`, so two drops by one run give
  two items (ADR-018).

**Merge verification**
- Import runs are admitted in `exported_on` order, then `started_at`, so
  import order matters only for runs sharing an export date, and a rebuild
  replays the same order (ADR-009 records the limits).
- A run is admitted only if it still shows every admitted transaction on its
  dates, and its end-of-day balances differ from the admitted ones by exactly
  the amounts it adds (*explained growth*, ADR-009): late bookings on earlier
  dates and later bookings on the export's final date both count. A date
  states an end-of-day balance only once it has a booked transaction, so
  balances are compared only on dates both sides state one; a null
  `end_of_day_balance` states none (ADR-016), and ADR-017 covers a date whose
  transactions the run all drops.
- A run *drops* a transaction when, on a covered date, it shows fewer booked
  transactions with that amount and identity text than are admitted. Each drop
  quarantines the run and raises one `dropped-transaction` item; dropped
  amounts count as explained, so a drop alone raises no `export-disagreement`.
  A *withdrawn* or *same transaction* decision settles an item, and the run is
  admitted once every item holding it is settled (ADR-017, ADR-018).
- An unexplained difference quarantines the later run and raises an
  `export-disagreement` review item.
- Silver uses balances only to verify its own merge. Coverage and
  reconciliation for reporting belong to Gold and analytics (ADR-006).

**Reproducibility**
- Rebuilding from the same Bronze inputs, account configuration, and manual
  decisions yields identical output, including identifiers.
- Silver is a function of a set of import runs. An as-known-at view derives
  Silver from the runs started by its cutoff, in a scratch store that the
  migrate runner creates and that leaves the current Silver untouched
  ([`publications.md`](publications.md#scratch-stores)).

## Downstream Requirements

Gold relies on a stable `transaction_id`, a deterministic order within each
account and date for the balance chain, the trimmed bank labels its
[rules](classification.md#what-a-rule-may-test) may test, and the
[evidence ranges and exports](#evidence-ranges).

## Responsibilities

- source-status mapping
- schema normalization and typing
- validation and quarantine
- duplicate resolution and merge verification
- lineage from every transaction to its source records

## Non-Responsibilities

- categorization
- budgeting
- reporting and coverage

## Ownership

Silver Agent
