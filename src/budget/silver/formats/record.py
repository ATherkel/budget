# Copyright 2026 Therkel
"""One source record read into typed, source-neutral values."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget.bronze.models import SourceRecord
from budget.silver.models import BookingStatus


@dataclass(frozen=True)
class ReadRecord:
    """What Silver needs from one valid source record, whatever its format."""

    record: SourceRecord
    transaction_date: date
    amount: Decimal
    balance: Decimal | None
    text: str
    category: str | None
    subcategory: str | None
    source_status: str
    booking_status: BookingStatus


@dataclass(frozen=True)
class RecordError:
    """One reason a source record cannot be read."""

    code: str
    message: str


@dataclass(frozen=True)
class ReadResult:
    """A record read, or every reason it could not be.

    `transaction_date` is kept whenever it reads, even if the record has
    other errors, because a run's `covered_from` counts every record.
    """

    transaction_date: date | None
    read: ReadRecord | None
    errors: tuple[RecordError, ...]
