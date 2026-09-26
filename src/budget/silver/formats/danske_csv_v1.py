# Copyright 2026 Therkel
"""`danske-csv-v1`, as `data-maps/danske-csv-v1-to-silver.md` maps it."""

import re
from datetime import date
from decimal import Decimal

from budget.bronze.models import SourceRecord
from budget.silver.formats.record import ReadRecord
from budget.silver.models import BookingStatus

# `[0-9]`, not `\d`: `\d` also matches digits from other scripts.
_DATE = re.compile(r"(?P<day>[0-9]{2})\.(?P<month>[0-9]{2})\.(?P<year>[0-9]{4})")
_DECIMAL = re.compile(
    r"(?P<sign>-?)(?P<whole>[0-9]+|[0-9]{1,3}(?:\.[0-9]{3})+)(?:,(?P<fraction>[0-9]+))?"
)
_BOOKING_STATUS: dict[str, BookingStatus] = {
    "Udført": "booked",
    "Slettet": "cancelled",
}


def read_record(record: SourceRecord, places: int) -> ReadRecord:
    """Read one record whose amounts carry `places` decimal places."""
    fields = record.fields
    saldo = fields["Saldo"]
    return ReadRecord(
        record=record,
        transaction_date=_read_date(fields["Dato"]),
        amount=_read_decimal(fields["Beløb"], places),
        balance=None if saldo == "" else _read_decimal(saldo, places),
        text=fields["Tekst"],
        category=_label(fields["Kategori"]),
        subcategory=_label(fields["Underkategori"]),
        source_status=fields["Status"],
        booking_status=_BOOKING_STATUS[fields["Status"]],
    )


def _read_date(value: str) -> date:
    """Read `DD.MM.YYYY`."""
    match = _DATE.fullmatch(value)
    if match is None:
        raise ValueError(value)
    return date(int(match["year"]), int(match["month"]), int(match["day"]))


def _read_decimal(value: str, places: int) -> Decimal:
    """Read a Danske decimal, padded to exactly `places` decimal places."""
    match = _DECIMAL.fullmatch(value)
    if match is None:
        raise ValueError(value)
    fraction = match["fraction"] or ""
    digits = match["whole"].replace(".", "") + fraction.ljust(places, "0")
    return Decimal(f"{match['sign']}{digits}").scaleb(-places)


def _label(value: str) -> str | None:
    """Trim a bank label; one that is empty afterwards is null."""
    return value.strip() or None
