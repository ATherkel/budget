# Copyright 2026 Therkel
"""`synthetic-ledger-v1`: a test-only second source format (#181).

It lives only in test code. Its records carry ISO dates, plain decimals and
English field names, so nothing here resembles `danske-csv-v1`. Every account,
text and amount is invented.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from budget.bronze.models import SourceRecord
from budget.bronze.parsers.base import ParserResult
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


HEADER = ("when", "sum", "memo", "bal", "state")
SEPARATOR = "\t"


def _absent(_named: str) -> None:
    """Say a filename or value carries nothing the format reads."""
    return


class Parser:
    """Bronze's side of the format: tab-separated lines under a fixed header."""

    source_format = FORMAT_ID

    def parse(self, content: bytes) -> ParserResult:
        """Split a payload into one record per line, keyed by the header."""
        lines = content.decode("utf-8").splitlines()
        if tuple(lines[0].split(SEPARATOR)) != HEADER:
            return ParserResult.failed("the header is not synthetic-ledger-v1's")
        records = tuple(
            dict(zip(HEADER, line.split(SEPARATOR), strict=True)) for line in lines[1:]
        )
        days = [date.fromisoformat(record["when"]) for record in records]
        return ParserResult.matched(
            records, min(days, default=None), max(days, default=None)
        )

    def exported_on_from_filename(self, filename: str) -> date | None:
        """The format names no export date in a filename."""
        return _absent(filename)

    def account_number_from_filename(self, filename: str) -> str | None:
        """The format names no account number in a filename."""
        return _absent(filename)

    def is_account_number(self, value: str) -> bool:
        """The format carries no account numbers."""
        return _absent(value) is not None


PARSER = Parser()


def payload(*rows: tuple[str, str, str, str]) -> bytes:
    """A payload of `(when, sum, memo, bal)` rows, all booked."""
    lines: list[str] = [SEPARATOR.join(HEADER)]
    lines += [SEPARATOR.join((*row, "booked")) for row in rows]
    return "\n".join(lines).encode("utf-8")
