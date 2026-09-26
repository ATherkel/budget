# Copyright 2026 Therkel
"""The Silver build: canonical records from a set of Bronze import runs."""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver.admission import Admission, Decisions, admit, judge
from budget.silver.decisions import (
    SilverDecision,
)
from budget.silver.identity import IDENTITY_VERSION
from budget.silver.merge import Ledger
from budget.silver.models import (
    AccountEvidence,
    BalanceObservation,
    ImportRunResult,
    SilverResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
)
from budget.silver.reading import ReadRun, Row, read_run


def build(
    *,
    runs: Sequence[ImportRun],
    source_records: Mapping[str, Sequence[SourceRecord]],
    format_failures: Mapping[str, Sequence[FormatFailure]],
    currencies: Mapping[str, str],
    decisions: Sequence[SilverDecision] = (),
) -> SilverResult:
    """Derive Silver from import runs, their payloads' records and currencies."""
    indexed = Decisions.of(decisions)
    runs = [r for r in runs if r.import_run_id not in indexed.voided]
    stored = sorted(
        (r for r in runs if r.outcome == "stored"),
        key=lambda r: (r.exported_on, r.started_at, r.import_run_id),
    )
    ledgers: dict[str, Ledger] = {}
    judged: list[Admission] = []
    for run in stored:
        each = read_run(
            run,
            source_records.get(run.payload_id, ()),
            format_failures.get(run.payload_id, ()),
            currencies,
        )
        ledger = ledgers.setdefault(each.account_id, Ledger(each.account_id))
        judged.append(admit(judge(each, indexed), ledger, indexed))
    admitted = [j.each for j in judged if j.admitted]
    return SilverResult(
        transactions=tuple(
            t for ledger in _sorted(ledgers) for t in _transactions(ledger)
        ),
        transaction_evidence=_evidence(ledgers, admitted),
        unbooked_records=tuple(
            sorted(
                (u for each in admitted for u in _unbooked(each)),
                key=lambda u: (u.payload_id, u.record_ordinal),
            )
        ),
        balance_observations=tuple(
            sorted(
                (o for each in admitted for o in _observations(each)),
                key=lambda o: (o.account_id, o.balance_date, o.payload_id),
            )
        ),
        account_evidence=_account_evidence(runs, admitted),
        import_run_results=tuple(
            sorted((_result(j) for j in judged), key=lambda r: r.import_run_id)
        ),
        review_items=tuple(
            sorted(
                (item for j in judged for item in j.review_items),
                key=lambda item: item.review_item_id,
            )
        ),
    )


def _sorted(ledgers: Mapping[str, Ledger]) -> list[Ledger]:
    return [ledgers[account_id] for account_id in sorted(ledgers)]


def _transactions(ledger: Ledger) -> list[Transaction]:
    """One transaction per kept identity, valued from its date's export."""
    return [
        _transaction(ledger.account_id, identifier, run, row, day_sequence)
        for identifier, run, row, day_sequence in ledger.kept()
    ]


def _transaction(
    account_id: str, identifier: str, run: ReadRun, row: Row, day_sequence: int
) -> Transaction:
    transaction_date, amount, description = row.key
    return Transaction(
        transaction_id=identifier,
        account_id=account_id,
        transaction_date=transaction_date,
        amount=amount,
        currency=run.currency,
        description=description,
        source_system=run.run.source_format,
        balance=row.record.balance,
        source_status=row.record.source_status,
        booking_status=row.record.booking_status,
        occurrence=row.occurrence,
        day_sequence=day_sequence,
        identity_version=IDENTITY_VERSION,
        bank_category=row.record.category,
        bank_subcategory=row.record.subcategory,
    )


def _evidence(
    ledgers: Mapping[str, Ledger], admitted: Iterable[ReadRun]
) -> tuple[TransactionEvidence, ...]:
    """Every admitted booked record, naming the kept transaction it shows."""
    return tuple(
        sorted(
            (
                TransactionEvidence(
                    transaction_id=ledgers[each.account_id].identify(
                        row.key, row.occurrence
                    ),
                    payload_id=each.run.payload_id,
                    record_ordinal=row.record.record.record_ordinal,
                    import_run_id=each.run.import_run_id,
                )
                for each in admitted
                for row in each.booked
                if ledgers[each.account_id].is_kept(row.key, row.occurrence)
            ),
            key=lambda e: (e.payload_id, e.record_ordinal),
        )
    )


def _unbooked(each: ReadRun) -> list[UnbookedRecord]:
    return [
        UnbookedRecord(
            payload_id=record.record.payload_id,
            record_ordinal=record.record.record_ordinal,
            import_run_id=each.run.import_run_id,
            account_id=each.account_id,
            transaction_date=record.transaction_date,
            amount=record.amount,
            source_status=record.source_status,
            booking_status=record.booking_status,
        )
        for record in each.records
        if record.booking_status != "booked"
    ]


def _observations(each: ReadRun) -> list[BalanceObservation]:
    """Each date's balance from its last booked row in payload order."""
    return [
        BalanceObservation(
            account_id=each.account_id,
            balance_date=balance_date,
            end_of_day_balance=balance,
            payload_id=each.run.payload_id,
        )
        for balance_date, balance in sorted(each.end_of_day.items())
    ]


def _account_evidence(
    runs: Iterable[ImportRun], admitted: Iterable[ReadRun]
) -> tuple[AccountEvidence, ...]:
    """Maximise the per-run formula of `silver-layer.md` (*Evidence Through*).

    Admitted runs count, and so do `repeat` runs of an admitted payload.
    """
    payloads = {(each.account_id, each.run.payload_id) for each in admitted}
    through: dict[str, date] = {}
    for run in runs:
        if run.outcome == "refused":
            continue
        if (run.declared_account_id, run.payload_id) not in payloads:
            continue
        bound = _evidence_through(run)
        account_id = run.declared_account_id
        through[account_id] = max(bound, through.get(account_id, bound))
    return tuple(
        AccountEvidence(account_id=account_id, evidence_through=bound)
        for account_id, bound in sorted(through.items())
    )


def _evidence_through(run: ImportRun) -> date:
    """Bound one run; an export proves nothing about its own production day."""
    if run.covers_through == run.exported_on:
        return run.covers_through - timedelta(days=1)
    return run.covers_through


def _result(judged: Admission) -> ImportRunResult:
    each = judged.each
    return ImportRunResult(
        import_run_id=each.run.import_run_id,
        status="accepted" if judged.admitted else "quarantined",
        covered_from=each.covered_from,
        covered_to=each.run.covers_through,
        errors=each.errors,
        review_item_ids=tuple(item.review_item_id for item in judged.review_items),
    )
