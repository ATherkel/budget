# Copyright 2026 Therkel
"""Danish display of dates and months, as the dashboard's reader sees them."""

from collections.abc import Iterator
from datetime import date, datetime

from budget.analytics import InvalidSelectionError
from budget.gold import ReportingMonth
from budget.timezone import COPENHAGEN

_MONTH_NAMES = (
    "januar",
    "februar",
    "marts",
    "april",
    "maj",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "december",
)


def copenhagen_date(now: datetime) -> date:
    """Return the date it is in Copenhagen at `now`."""
    return now.astimezone(COPENHAGEN).date()


def danish_date(day: date) -> str:
    """Return a date as a Danish reader reads it, such as `03.02.2026`."""
    return day.strftime("%d.%m.%Y")


def month_value(month: ReportingMonth) -> str:
    """Return a month as a form submits it, `YYYY-MM`."""
    return f"{month.year:04d}-{month.month:02d}"


def parse_month(value: str) -> ReportingMonth:
    """Return the month a form submitted as `YYYY-MM`.

    Text that names no calendar month is, like a month outside the range, a
    month that cannot be chosen: `InvalidSelectionError` with
    `month_out_of_range`.
    """
    try:
        year, month = value.split("-")
        return ReportingMonth(int(year), int(month))
    except ValueError:
        raise InvalidSelectionError(["month_out_of_range"]) from None


def month_label(month: ReportingMonth) -> str:
    """Return a month as a Danish reader reads it, such as `juni 2026`."""
    return f"{_MONTH_NAMES[month.month - 1]} {month.year}"


def period_label(first: ReportingMonth, last: ReportingMonth) -> str:
    """Return a period within one year: `januar 2026`, or January to February.

    A span joins its months with an en dash, as Danish writes a range.
    """
    if first == last:
        return month_label(last)
    return f"{_MONTH_NAMES[first.month - 1]}\N{EN DASH}{month_label(last)}"


def months_between(
    first: ReportingMonth, last: ReportingMonth
) -> Iterator[ReportingMonth]:
    """Yield every month from `first` through `last`, oldest first."""
    months_in_year = len(_MONTH_NAMES)
    start = first.year * months_in_year + first.month - 1
    stop = last.year * months_in_year + last.month
    for index in range(start, stop):
        year, month = divmod(index, months_in_year)
        yield ReportingMonth(year, month + 1)
