# Copyright 2026 Therkel
"""The Silver build: canonical records from a set of Bronze import runs."""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver.balances import BALANCE_BREAK_CODES, chain_errors
from budget.silver.currencies import minor_unit_places
from budget.silver.decisions import SilverDecision
from budget.silver.formats import FORMATS, ReadRecord, RecordError
from budget.silver.identity import (
    IDENTITY_VERSION,
    identity_text,
    review_item_id,
    transaction_id,
)
from budget.silver.models import (
    AccountEvidence,
    BalanceObservation,
    ImportRunResult,
    ReviewItem,
    SilverResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
    ValidationError,
)

if TYPE_CHECKING:
    from decimal import Decimal


@dataclass(frozen=True)
class _Run:
    """One stored import run with its payload's records read and validated."""

    run: ImportRun
    currency: str
    records: tuple[ReadRecord, ...]
    covered_from: date | None
    errors: tuple[ValidationError, ...]
    # The transaction dates of the rows with a balance break, if any.
    break_dates: tuple[date, ...]

    @property
    def booked(self) -> tuple[ReadRecord, ...]:
        """The records that are booked transactions, in payload order."""
        return tuple(r for r in self.records if r.booking_status == "booked")


@dataclass(frozen=True)
class _Judged:
    """A run with the review items it raised and whether it is admitted."""

    each: _Run
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
    # Every Silver decision so far is *accept discrepancy*; later kinds filter.
    accepted = {d.import_run_id: d.decision_id for d in decisions}
    judged = [
        _judge(
            _read_run(
                run,
                source_records.get(run.payload_id, ()),
                format_failures.get(run.payload_id, ()),
                currencies,
            ),
            accepted,
        )
        for run in runs
        if run.outcome == "stored"
    ]
    admitted = [j.each for j in judged if j.admitted]
    transactions: list[Transaction] = []
    evidence: list[TransactionEvidence] = []
    for each in admitted:
        found, shown = _transactions(each)
        transactions.extend(found)
        evidence.extend(shown)
    return SilverResult(
        transactions=tuple(
            sorted(
                transactions,
                key=lambda t: (t.account_id, t.transaction_date, t.day_sequence),
            )
        ),
        transaction_evidence=tuple(
            sorted(evidence, key=lambda e: (e.payload_id, e.record_ordinal))
        ),
        unbooked_records=tuple(u for each in admitted for u in _unbooked(each)),
        balance_observations=tuple(o for each in admitted for o in _observations(each)),
        account_evidence=_account_evidence(each.run for each in admitted),
        import_run_results=tuple(_result(j) for j in judged),
        review_items=tuple(
            sorted(
                (item for j in judged for item in j.review_items),
                key=lambda item: item.review_item_id,
            )
        ),
    )


def _read_run(
    run: ImportRun,
    records: Sequence[SourceRecord],
    failures: Sequence[FormatFailure],
    currencies: Mapping[str, str],
) -> _Run:
    """Read every record of a run, keeping each error against its record."""
    currency = currencies[run.declared_account_id]
    source_format = FORMATS[run.source_format]
    places = minor_unit_places(currency)
    results = [source_format.read(record, places) for record in records]
    found: list[tuple[int | None, RecordError]] = [
        (None, RecordError("format-failure", failure.reason)) for failure in failures
    ]
    found.extend(
        (record.record_ordinal, error)
        for record, result in zip(records, results, strict=True)
        for error in result.errors
    )
    breaks = (
        chain_errors(result.read for result in results)
        if source_format.states_balances
        else []
    )
    found.extend((record.record.record_ordinal, error) for record, error in breaks)
    # Payload-level errors first, then by record; each record's in field order.
    found.sort(key=lambda pair: -1 if pair[0] is None else pair[0])
    return _Run(
        run=run,
        currency=currency,
        records=tuple(r.read for r in results if r.read is not None),
        covered_from=min(
            (d for r in results if (d := r.transaction_date) is not None),
            default=None,
        ),
        errors=tuple(
            ValidationError(run.payload_id, ordinal, error.code, error.message)
            for ordinal, error in found
        ),
        break_dates=tuple(record.transaction_date for record, _ in breaks),
    )


def _judge(each: _Run, accepted: Mapping[str, str]) -> _Judged:
    """Raise the run's review items and admit it if they settle every error."""
    if not each.break_dates:
        return _Judged(each=each, review_items=(), admitted=not each.errors)
    resolved_by = accepted.get(each.run.import_run_id)
    item = ReviewItem(
        review_item_id=review_item_id("balance-break", each.run.import_run_id),
        kind="balance-break",
        account_id=each.run.declared_account_id,
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


def _transactions(
    each: _Run,
) -> tuple[list[Transaction], list[TransactionEvidence]]:
    """One transaction per booked record of a single export, with its evidence."""
    account_id = each.run.declared_account_id
    occurrences: Counter[tuple[date, Decimal, str]] = Counter()
    day_sequences: Counter[date] = Counter()
    transactions: list[Transaction] = []
    evidence: list[TransactionEvidence] = []
    for record in each.booked:
        description = identity_text(record.text)
        occurrences[record.transaction_date, record.amount, description] += 1
        day_sequences[record.transaction_date] += 1
        occurrence = occurrences[record.transaction_date, record.amount, description]
        identifier = transaction_id(
            account_id, record.transaction_date, record.amount, description, occurrence
        )
        transactions.append(
            Transaction(
                transaction_id=identifier,
                account_id=account_id,
                transaction_date=record.transaction_date,
                amount=record.amount,
                currency=each.currency,
                description=description,
                source_system=each.run.source_format,
                balance=record.balance,
                source_status=record.source_status,
                booking_status=record.booking_status,
                occurrence=occurrence,
                day_sequence=day_sequences[record.transaction_date],
                identity_version=IDENTITY_VERSION,
                bank_category=record.category,
                bank_subcategory=record.subcategory,
            )
        )
        evidence.append(
            TransactionEvidence(
                transaction_id=identifier,
                payload_id=record.record.payload_id,
                record_ordinal=record.record.record_ordinal,
                import_run_id=each.run.import_run_id,
            )
        )
    return transactions, evidence


def _unbooked(each: _Run) -> list[UnbookedRecord]:
    return [
        UnbookedRecord(
            payload_id=record.record.payload_id,
            record_ordinal=record.record.record_ordinal,
            import_run_id=each.run.import_run_id,
            account_id=each.run.declared_account_id,
            transaction_date=record.transaction_date,
            amount=record.amount,
            source_status=record.source_status,
            booking_status=record.booking_status,
        )
        for record in each.records
        if record.booking_status != "booked"
    ]


def _observations(each: _Run) -> list[BalanceObservation]:
    """Each date's balance from its last booked row in payload order."""
    last_booked = {record.transaction_date: record for record in each.booked}
    return [
        BalanceObservation(
            account_id=each.run.declared_account_id,
            balance_date=balance_date,
            end_of_day_balance=record.balance,
            payload_id=each.run.payload_id,
        )
        for balance_date, record in sorted(last_booked.items())
    ]


def _account_evidence(runs: Iterable[ImportRun]) -> tuple[AccountEvidence, ...]:
    """Maximise the per-run formula of `silver-layer.md` (*Evidence Through*)."""
    through: dict[str, date] = {}
    for run in runs:
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
