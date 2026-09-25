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
  - *withdrawn*: the bank removed a transaction. It also settles a
    `fewer-repeats` review item and admits the export that showed fewer.
  - *accept discrepancy*: an import run's balance break is real in the source
    and is admitted with the break recorded (ADR-010).

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
    bank_category: str | None,  # provenance only; trimmed
    bank_subcategory: str | None,
)
```

`balance` is the bank-stated account balance immediately after this
transaction. `source_status` is the source's own status value, carried
verbatim. `description` is the identity text defined in ADR-009: the source
text with leading and trailing whitespace removed and internal runs collapsed
to one space. Every export that shows a transaction therefore gives it the same
`description`, and a later export never changes it; Bronze keeps the text as
delivered, reachable through `TransactionEvidence`. For each date, `balance`,
`day_sequence`, `bank_category` and `bank_subcategory` come from the latest
admitted export covering that date (ADR-009). They can therefore change when a
later export adds a late-booked transaction or relabels one; `transaction_id`
never does.
`balance` is null only for sources that state no balances (ADR-010). The export
chosen for a date is the latest admitted one that shows every transaction kept
for it.

Within a date, `day_sequence` preserves the bank's row order in the selected
export; it is never sorted by amount or text. A transaction kept for that date
that the selected export does not show is appended after that export's rows, in
`transaction_id` order. It is never numbered from its occurrence *k*: two
appended transactions on one date can share a *k*, and `(account_id,
transaction_date, day_sequence)` has to stay unique, because Gold numbers
`account_sequence` from that order (`gold-contract.md` invariant 7). Under the
rules below the selected export always does show every transaction kept for its
dates, so this is a guard and not a path — but it is
written down because the obvious numbering is the colliding one.

## Evidence Through

Silver computes each account's evidence bound and passes it forward as
`AccountEvidence`. This is the single definition of the rule; `gold-contract.md`,
ADR-006 and `CONTEXT.md` cite it instead of restating it, and Gold carries the
value through to `GoldAccount.evidence_through` unchanged rather than deriving
it again.

```text
evidence_through(account) = max over that account's admitted import runs of:
    covers_through - 1 day   when covers_through == exported_on
    covers_through           otherwise
```

The adjustment is applied **per run, before the maximum**, never to the maximum
afterwards. An export that reaches its own production day proves nothing about
that day, because the day may still be booking; an export whose range ended
earlier proves its whole range. Taking the maximum first would let one run's
production-day adjustment truncate another run's fully proven range, or hide a
production-day run behind an earlier one.

`repeat` runs of an already admitted payload count here: they carry their own
`exported_on` and `covers_through` without contributing source records, which is
how an account with no new activity extends its evidence. An account with no
admitted import run produces no `AccountEvidence`, and
`GoldAccount.evidence_through` is null.

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
    end_of_day_balance: Decimal,
    payload_id: str,
)

AccountEvidence(                # the account's evidence bound; see above
    account_id: str,
    evidence_through: date,     # computed by the formula in Evidence Through
)

ImportRunResult(
    import_run_id: str,
    status: Literal["accepted", "quarantined"],
    covered_from: date,         # first transaction date in the export
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
    kind: Literal["export-disagreement", "fewer-repeats", "balance-break"],
    account_id: str,
    date_from: date,
    date_to: date,
    payload_ids: Sequence[str],
    resolved_by: str | None,    # manual decision id
)
```

## Rules

**Booking state**
- Each source format maps its status values to `booking_status`: `booked`,
  `pending`, or `cancelled`. For `danske-csv-v1`, `Udført` is `booked` and
  `Slettet` is `cancelled`. Only booked rows enter the canonical transaction
  output; pending and cancelled rows remain `UnbookedRecord` provenance.
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
    export (ADR-010).
- A booked row without a balance, or a chain break within the export, also
  raises a `balance-break` review item for that run alongside the validation
  errors. The errors say what is wrong with the file; the review item is what
  an *accept discrepancy* decision is prompted by and attaches to through
  `resolved_by` (ADR-010). Without it the quarantine is the only signal, and
  nothing in the operator's work list says there is a way back.

**Identity and merging**
- Per ADR-009: content plus occurrence identity, and the highest count per
  export when exports overlap.

**Merge verification**
- Import runs are admitted in `exported_on` order, then `started_at` for runs
  produced on the same date. For runs the bank produced on different days the
  household's import order therefore does not change the outcome, and a rebuild
  after a late-arriving older export replays every run in that same order
  (ADR-009). Runs sharing an `exported_on` fall back to import order; ADR-009
  records what that can and cannot change.
- A run is admitted only if it still shows every transaction already admitted
  for the dates it covers, and its end-of-day balances differ from those
  already admitted by exactly the cumulative amounts of the transactions it
  adds (*explained growth*, ADR-009). Late bookings on earlier dates, and
  later bookings on an export's final date, are both explained growth. A date
  states an end-of-day balance only once it has a booked transaction, so the
  balances are compared on the dates both sides state one; ADR-009 records why
  that is a consequence of the rules above and not an exemption from them.
- An unexplained difference quarantines the later run and raises an
  `export-disagreement` review item.
- Fewer repeated transactions on any date quarantine the run and raise a
  `fewer-repeats` review item; the amounts of the missing repeats count as an
  explained difference, so the same date raises no `export-disagreement`.
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

Gold relies on three guarantees that Silver provides under
[ADR-009](../decisions/ADR-009-transaction-identity.md):

- a stable canonical identity for each transaction, from which Gold derives a
  `transaction_id` that survives rebuilds;
- a deterministic order of each account's transactions, including those
  sharing a transaction date, so Gold can evaluate the balance chain;
- the source's category labels as trimmed Silver provenance (`bank_category`
  and `bank_subcategory`), which Gold rules may test; Bronze preserves the
  original labels ([`classification.md`](classification.md)).

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
