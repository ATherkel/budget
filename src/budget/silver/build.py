# Copyright 2026 Therkel
"""The Silver build: canonical records from a set of Bronze import runs."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver.balances import BALANCE_BREAK_CODES
from budget.silver.decisions import AcceptDiscrepancy, SilverDecision
from budget.silver.identity import IDENTITY_VERSION, review_item_id
from budget.silver.merge import Ledger
from budget.silver.models import (
    AccountEvidence,
    BalanceObservation,
    ImportRunResult,
    ReviewItem,
    SilverResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
)
from budget.silver.reading import ReadRun, Row, read_run


@dataclass(frozen=True)
class _Judged:
    """A run with the review items it raised and whether it is admitted."""

    each: ReadRun
    review_items: tuple[ReviewItem, ...]
    admitted: bool


def build(
    *,
    runs: Sequence[ImportRun],
    source_records: Mapping[str, Sequence[SourceRecord]],
    format_failures: Mapping[str, Sequence[FormatFailure]],
    currencies: Mapping[str, str],
    decisions: Sequence[SilverDecision] = (),
) -> SilverResult:
    """Derive Silver from import runs, their payloads' records and currencies."""
    accepted = {
        d.import_run_id: d.decision_id
        for d in decisions
        if isinstance(d, AcceptDiscrepancy)
    }
    stored = sorted(
        (r for r in runs if r.outcome == "stored"),
        key=lambda r: (r.exported_on, r.started_at, r.import_run_id),
    )
    ledgers: dict[str, Ledger] = {}
    judged: list[_Judged] = []
    for run in stored:
        each = read_run(
            run,
            source_records.get(run.payload_id, ()),
            format_failures.get(run.payload_id, ()),
            currencies,
        )
        ledger = ledgers.setdefault(each.account_id, Ledger(each.account_id))
        judged.append(_admit(_judge(each, accepted), ledger))
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


def _judge(each: ReadRun, accepted: Mapping[str, str]) -> _Judged:
    """Raise the run's own review items and admit it if they settle its errors."""
    if not each.break_dates:
        return _Judged(each=each, review_items=(), admitted=not each.errors)
    resolved_by = accepted.get(each.run.import_run_id)
    item = ReviewItem(
        review_item_id=review_item_id("balance-break", each.run.import_run_id),
        kind="balance-break",
        account_id=each.account_id,
        date_from=min(each.break_dates),
        date_to=max(each.break_dates),
        payload_ids=(each.run.payload_id,),
        resolved_by=resolved_by,
    )
    settled = BALANCE_BREAK_CODES if resolved_by is not None else frozenset()
    return _Judged(
        each=each,
        review_items=(item,),
        admitted=all(error.code in settled for error in each.errors),
    )


def _admit(judged: _Judged, ledger: Ledger) -> _Judged:
    """Admit a valid run whose merge with what is admitted verifies."""
    if not judged.admitted:
        return judged
    verdict = ledger.verdict(judged.each)
    if verdict.clean:
        ledger.admit(judged.each)
        return judged
    items = judged.review_items
    if verdict.disagreements:
        items = (*items, _disagreement(judged.each, verdict.disagreements))
    return _Judged(each=judged.each, review_items=items, admitted=False)


def _disagreement(
    each: ReadRun, disagreements: Sequence[tuple[date, str]]
) -> ReviewItem:
    """Raise the item for balances unexplained by every added and dropped amount."""
    days = [day for day, _ in disagreements]
    compared = sorted({payload_id for _, payload_id in disagreements})
    return ReviewItem(
        review_item_id=review_item_id("export-disagreement", each.run.import_run_id),
        kind="export-disagreement",
        account_id=each.account_id,
        date_from=min(days),
        date_to=max(days),
        payload_ids=(each.run.payload_id, *compared),
        resolved_by=None,
    )


def _sorted(ledgers: Mapping[str, Ledger]) -> list[Ledger]:
    return [ledgers[account_id] for account_id in sorted(ledgers)]


def _transactions(ledger: Ledger) -> list[Transaction]:
    """One transaction per admitted identity, valued from its date's export."""
    return [
        _transaction(ledger, identifier, row, day_sequence)
        for identifier, row, day_sequence in ledger.kept()
    ]


def _transaction(
    ledger: Ledger, identifier: str, row: Row, day_sequence: int
) -> Transaction:
    run = next(r for r in ledger.admitted if row in r.booked)
    transaction_date, amount, description = row.key
    return Transaction(
        transaction_id=identifier,
        account_id=ledger.account_id,
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
    """Every admitted booked record, naming the transaction it shows."""
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
    payloads = {each.run.payload_id for each in admitted}
    through: dict[str, date] = {}
    for run in runs:
        if run.outcome == "refused" or run.payload_id not in payloads:
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


def _result(judged: _Judged) -> ImportRunResult:
    each = judged.each
    return ImportRunResult(
        import_run_id=each.run.import_run_id,
        status="accepted" if judged.admitted else "quarantined",
        covered_from=each.covered_from,
        covered_to=each.run.covers_through,
        errors=each.errors,
        review_item_ids=tuple(item.review_item_id for item in judged.review_items),
    )
