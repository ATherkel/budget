# Copyright 2026 Therkel
"""`synthetic-ledger-v1`: a test-only second source format (#181).

It lives only in test code. Its records carry ISO dates, plain decimals and
English field names, so nothing here resembles `danske-csv-v1`. Every account,
text and amount is invented.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from budget.bronze.models import SourceRecord
from budget.silver.formats import SourceFormat
from budget.silver.formats.record import ReadRecord, ReadResult, RecordError
from budget.silver.models import BookingStatus

FORMAT_ID = "synthetic-ledger-v1"

_STATUS: dict[str, BookingStatus] = {"booked": "booked", "pending": "pending"}


def read_record(record: SourceRecord, _places: int) -> ReadResult:
    """Read one record of the format; `_places` is unused as amounts are plain."""
    fields = record.fields
    try:
        transaction_date = date.fromisoformat(fields["when"])
        amount = Decimal(fields["sum"])
        balance = Decimal(fields["bal"]) if fields["bal"] else None
        booking_status = _STATUS[fields["state"]]
    except (KeyError, ValueError, InvalidOperation):
        error = RecordError("invalid-record", "record is not synthetic-ledger-v1")
        return ReadResult(read=None, errors=(error,))
    read = ReadRecord(
        record=record,
        transaction_date=transaction_date,
        amount=amount,
        balance=balance,
        text=fields["memo"],
        category=None,
        subcategory=None,
        source_status=fields["state"],
        booking_status=booking_status,
    )
    return ReadResult(read=read, errors=())


FORMAT = SourceFormat(
    read=read_record,
    has_labels=lambda _record: False,
    states_balances=True,
)
