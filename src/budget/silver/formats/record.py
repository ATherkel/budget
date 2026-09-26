# Copyright 2026 Therkel
"""One source record read into typed, source-neutral values."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from budget.bronze.models import SourceRecord
from budget.silver.models import BookingStatus


@dataclass(frozen=True)
class ReadRecord:
    """What Silver needs from one source record, whatever its format."""

    record: SourceRecord
    transaction_date: date
    amount: Decimal
    balance: Decimal | None
    text: str
    category: str | None
    subcategory: str | None
    source_status: str
    booking_status: BookingStatus
