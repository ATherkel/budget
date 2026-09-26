# Copyright 2026 Therkel
"""`danske-csv-v1`, as `data-maps/danske-csv-v1-to-silver.md` maps it."""

import re
from datetime import date
from decimal import Decimal

from budget.bronze.models import SourceRecord
from budget.silver.formats.record import ReadRecord, ReadResult, RecordError
from budget.silver.models import BookingStatus

_HEADER = frozenset(
    (
        "Dato",
        "Kategori",
        "Underkategori",
        "Tekst",
        "Beløb",
        "Saldo",
        "Status",
        "Afstemt",
    )
)
# `[0-9]`, not `\d`: `\d` also matches digits from other scripts.
_DATE = re.compile(r"(?P<day>[0-9]{2})\.(?P<month>[0-9]{2})\.(?P<year>[0-9]{4})")
_DECIMAL = re.compile(
    r"(?P<sign>-?)(?P<whole>[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)(?:,(?P<fraction>[0-9]+))?"
)
_BOOKING_STATUS: dict[str, BookingStatus] = {
    "Udført": "booked",
    "Slettet": "cancelled",
}


def read_record(record: SourceRecord, places: int) -> ReadResult:
    """Read one record whose amounts carry `places` decimal places."""
    fields = record.fields
    if fields.keys() != _HEADER:
        error = RecordError("wrong-field-count", "fields are not the format's header")
        return ReadResult(transaction_date=None, read=None, errors=(error,))
    errors: list[RecordError] = []
    transaction_date = _read_date(fields["Dato"], errors)
    amount = _read_decimal("Beløb", fields["Beløb"], places, errors)
    booking_status = _BOOKING_STATUS.get(fields["Status"])
    balance = None
    if booking_status == "booked" and fields["Saldo"] != "":
        balance = _read_decimal("Saldo", fields["Saldo"], places, errors)
    if booking_status is None:
        errors.append(RecordError("unknown-status", "Status has no booking status"))
    if errors or transaction_date is None or amount is None or booking_status is None:
        return ReadResult(
            transaction_date=transaction_date, read=None, errors=(*errors,)
        )
    read = ReadRecord(
        record=record,
        transaction_date=transaction_date,
        amount=amount,
        balance=balance,
        text=fields["Tekst"],
        category=_label(fields["Kategori"]),
        subcategory=_label(fields["Underkategori"]),
        source_status=fields["Status"],
        booking_status=booking_status,
    )
    return ReadResult(transaction_date=transaction_date, read=read, errors=())


def _read_date(value: str, errors: list[RecordError]) -> date | None:
    """Read `DD.MM.YYYY`, a real calendar date, or record why not."""
    match = _DATE.fullmatch(value)
    try:
        if match is not None:
            return date(int(match["year"]), int(match["month"]), int(match["day"]))
    except ValueError:
        pass
    errors.append(RecordError("unparseable-date", "Dato is not a DD.MM.YYYY date"))
    return None


def _read_decimal(
    name: str, value: str, places: int, errors: list[RecordError]
) -> Decimal | None:
    """Read a Danske decimal padded to exactly `places` places, or record why not."""
    match = _DECIMAL.fullmatch(value)
    fraction = "" if match is None else match["fraction"] or ""
    if match is None or len(fraction) > places:
        errors.append(
            RecordError(
                "unparseable-decimal", f"{name} is not a decimal in its currency"
            )
        )
        return None
    digits = match["whole"].replace(".", "") + fraction.ljust(places, "0")
    return Decimal(f"{match['sign']}{digits}").scaleb(-places)


def _label(value: str) -> str | None:
    """Trim a bank label; one that is empty afterwards is null."""
    return value.strip() or None
