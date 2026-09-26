# Copyright 2026 Therkel
"""Reading and validating one stored import run on its own."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget.bronze.models import FormatFailure, ImportRun, SourceRecord
from budget.silver.balances import chain_errors
from budget.silver.currencies import minor_unit_places
from budget.silver.formats import FORMATS, ReadRecord, RecordError
from budget.silver.identity import identity_text
from budget.silver.models import ValidationError

# ADR-009's identity inputs other than the account and occurrence:
# transaction date, amount and identity text.
type Key = tuple[date, Decimal, str]


@dataclass(frozen=True)
class Row:
    """One booked row of an export, with its place in the export."""

    record: ReadRecord
    key: Key
    occurrence: int  # k among this export's rows sharing the key
    position: int  # 1-based among this export's booked rows on its date


@dataclass(frozen=True)
class ReadRun:
    """One stored import run with its payload's records read and validated."""

    run: ImportRun
    currency: str
    records: tuple[ReadRecord, ...]
    booked: tuple[Row, ...]
    covered_from: date | None
    errors: tuple[ValidationError, ...]
    # The transaction dates of the rows with a balance break, if any.
    break_dates: tuple[date, ...]

    @property
    def account_id(self) -> str:
        """The account the operator declared the run for."""
        return self.run.declared_account_id

    @property
    def end_of_day(self) -> dict[date, Decimal | None]:
        """Each date's balance from its last booked row in payload order."""
        return {row.record.transaction_date: row.record.balance for row in self.booked}

    def covers(self, day: date) -> bool:
        """Whether `day` lies within the dates this export covers."""
        return self.covered_from is not None and (
            self.covered_from <= day <= self.run.covers_through
        )


def read_run(
    run: ImportRun,
    records: Sequence[SourceRecord],
    failures: Sequence[FormatFailure],
    currencies: Mapping[str, str],
) -> ReadRun:
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
    read = tuple(r.read for r in results if r.read is not None)
    return ReadRun(
        run=run,
        currency=currency,
        records=read,
        booked=_rows(read),
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


def _rows(records: Sequence[ReadRecord]) -> tuple[Row, ...]:
    """Give each booked record its occurrence and its position in its day."""
    occurrences: Counter[Key] = Counter()
    positions: Counter[date] = Counter()
    rows: list[Row] = []
    for record in records:
        if record.booking_status != "booked":
            continue
        key = (record.transaction_date, record.amount, identity_text(record.text))
        occurrences[key] += 1
        positions[record.transaction_date] += 1
        rows.append(
            Row(
                record=record,
                key=key,
                occurrence=occurrences[key],
                position=positions[record.transaction_date],
            )
        )
    return tuple(rows)
