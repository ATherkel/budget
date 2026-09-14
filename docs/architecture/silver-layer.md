# Silver Layer

## Purpose

Convert source records into validated, source-neutral canonical records, and
resolve which source records show the same booked transaction.

## Inputs

- Bronze import runs with outcome `stored` that have not been voided, with
  their source records or format failures.
- Account configuration: each account's currency.
- Manual decisions that affect identity. Their file format belongs to issue #10.
  - *void import run*
  - *same transaction*: a source record shows an existing transaction.
  - *withdrawn*: the bank removed a transaction.

## Canonical Transaction

One record per booked transaction, after duplicates are collapsed.

```python
Transaction(
    transaction_id: str,        # ADR-007 identity hash
    account_id: str,
    booking_date: date,
    amount: Decimal,
    currency: str,              # from account configuration
    description: str,           # source text exactly as delivered
    source_system: str,         # source format, e.g. "danske-csv-v1"
    balance: Decimal | None,
    source_status: str,
    occurrence: int,            # k among visibly identical transactions
    day_sequence: int,          # order within booking_date
    identity_version: str,
    bank_category: str | None,  # provenance only; trimmed
    bank_subcategory: str | None,
)
```

`balance` is the bank-stated account balance immediately after this
transaction. `source_status` is the source's own status value, carried
verbatim. For each date, `balance` and `day_sequence` come from one export,
chosen as ADR-007 describes. `balance` is null only for sources that state no
balances (ADR-008).

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
    source_date: date,
    amount: Decimal,
    source_status: str,
)

BalanceObservation(             # bank-stated end-of-day balance per export
    account_id: str,
    balance_date: date,
    end_of_day_balance: Decimal,
    payload_id: str,
    is_final_date: bool,        # the export's last date may be incomplete
)

ImportRunResult(
    import_run_id: str,
    status: Literal["accepted", "quarantined"],
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
    kind: Literal["export-disagreement", "fewer-repeats"],
    account_id: str,
    date_from: date,
    date_to: date,
    payload_ids: Sequence[str],
    resolved_by: str | None,    # manual decision id
)
```

## Rules

**Booking state**
- Each source format maps its status values to booked or unbooked. For
  `danske-csv-v1`, `Udført` is booked and `Slettet` is unbooked.
- An unknown status value is a validation error. Gold never sees a source
  status vocabulary.
- `Afstemt` is retained in Bronze only and is not interpreted.

**Validation**
- An import run is admitted whole or quarantined whole, with every error
  listed against its source record. Nothing is partially imported.
- Errors include:
  - a format failure;
  - a wrong field count;
  - an unparseable date or decimal;
  - an unknown status;
  - a booked row without a balance, or a balance-chain break within the
    export (ADR-008).

**Identity and merging**
- Per ADR-007: content plus occurrence identity, and the highest count per
  export when exports overlap.

**Merge verification**
- Import runs are admitted in `started_at` order. Each is admitted only if its
  balance observations agree with those of the runs already admitted, apart
  from final dates.
- A disagreement quarantines the later run and raises an `export-disagreement`
  review item.
- Fewer repeated transactions on a non-final date raises a `fewer-repeats`
  review item.
- Silver uses balances only to verify its own merge. Coverage and
  reconciliation for reporting belong to Gold and analytics (ADR-006).

**Reproducibility**
- Rebuilding from the same Bronze inputs, account configuration, and manual
  decisions yields identical output, including identifiers.

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
