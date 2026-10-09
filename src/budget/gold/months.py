# Copyright 2026 Therkel
"""Calendar arithmetic on `ReportingMonth`, for the build's monthly facts."""

from collections.abc import Iterator
from datetime import date, timedelta

from budget.gold.models import ReportingMonth

_MONTHS_IN_A_YEAR = 12


def first_day(month: ReportingMonth) -> date:
    """Return the month's first day."""
    return date(month.year, month.month, 1)


def last_day(month: ReportingMonth) -> date:
    """Return the month's last day."""
    return first_day(_following(month)) - timedelta(days=1)


def months_through(
    first: ReportingMonth, last: ReportingMonth
) -> Iterator[ReportingMonth]:
    """Yield every month from `first` through `last`; none when `last` is earlier."""
    month = first
    while month <= last:
        yield month
        month = _following(month)


def _following(month: ReportingMonth) -> ReportingMonth:
    # Months counted from 1 become 0-11 past each year's December.
    year, index = divmod(
        month.year * _MONTHS_IN_A_YEAR + month.month, _MONTHS_IN_A_YEAR
    )
    return ReportingMonth(year, index + 1)
