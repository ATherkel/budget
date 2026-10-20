# Copyright 2026 Therkel
"""Danish display of dates and months, as the dashboard's reader sees them."""

from collections.abc import Iterator
from datetime import date, datetime
from zoneinfo import ZoneInfo

from budget.analytics import InvalidSelectionError
from budget.gold import ReportingMonth

COPENHAGEN = ZoneInfo("Europe/Copenhagen")

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


def month_value(month: ReportingMonth) -> str:
    """Return a month as a form submits it, `YYYY-MM`."""
    return f"{month.year:04d}-{month.month:02d}"


def selection_problems(error: InvalidSelectionError) -> list[str]:
    """Return a Danish sentence for every selection rule `error` names."""
    problems = [
        f"Kontoen {account_id} findes ikke i disse tal."
        for account_id in error.unknown_account_ids
    ]
    if "month_out_of_range" in error.reasons:
        problems.append("Den valgte måned ligger uden for de måneder, der kan vælges.")
    return problems


def parse_month(value: str) -> ReportingMonth:
    """Return the month a form submitted as `YYYY-MM`."""
    year, month = value.split("-")
    return ReportingMonth(int(year), int(month))


def month_label(month: ReportingMonth) -> str:
    """Return a month as a Danish reader reads it, such as `juni 2026`."""
    return f"{_MONTH_NAMES[month.month - 1]} {month.year}"


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
