# Copyright 2026 Therkel
"""The Silver build: canonical records from a set of Bronze import runs."""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver.currencies import minor_unit_places
from budget.silver.formats import READERS, ReadRecord
from budget.silver.identity import IDENTITY_VERSION, identity_text, transaction_id
from budget.silver.models import (
    AccountEvidence,
    BalanceObservation,
    ImportRunResult,
    SilverResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
)

if TYPE_CHECKING:
    from decimal import Decimal


@dataclass(frozen=True)
class _Run:
    """One stored import run with its payload's records read."""

    run: ImportRun
    currency: str
    records: tuple[ReadRecord, ...]

    @property
    def booked(self) -> tuple[ReadRecord, ...]:
        """The records that are booked transactions, in payload order."""
        return tuple(r for r in self.records if r.booking_status == "booked")


def build(
    *,
    runs: Sequence[ImportRun],
    source_records: Mapping[str, Sequence[SourceRecord]],
    format_failures: Mapping[str, Sequence[FormatFailure]],
    currencies: Mapping[str, str],
) -> SilverResult:
    """Derive Silver from import runs, their payloads' records and currencies."""
    del format_failures  # Validation (#91) reads them.
    read = [
        _read_run(run, source_records[run.payload_id], currencies)
        for run in runs
        if run.outcome == "stored"
    ]
    transactions: list[Transaction] = []
    evidence: list[TransactionEvidence] = []
    for each in read:
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
        unbooked_records=tuple(u for each in read for u in _unbooked(each)),
        balance_observations=tuple(o for each in read for o in _observations(each)),
        account_evidence=_account_evidence(each.run for each in read),
        import_run_results=tuple(_result(each) for each in read),
        review_items=(),
    )


def _read_run(
    run: ImportRun, records: Sequence[SourceRecord], currencies: Mapping[str, str]
) -> _Run:
    currency = currencies[run.declared_account_id]
    places = minor_unit_places(currency)
    reader = READERS[run.source_format]
    return _Run(
        run=run,
        currency=currency,
        records=tuple(reader(record, places) for record in records),
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


def _result(each: _Run) -> ImportRunResult:
    return ImportRunResult(
        import_run_id=each.run.import_run_id,
        status="accepted",
        covered_from=min(
            (record.transaction_date for record in each.records), default=None
        ),
        covered_to=each.run.covers_through,
        errors=(),
        review_item_ids=(),
    )
