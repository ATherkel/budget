# Copyright 2026 Therkel
"""The Gold contract records and `ReportingMonth` (`gold-contract.md`)."""

from datetime import date
from typing import TypeAliasType, get_args, get_type_hints

import budget.gold
from budget.gold import ReportingMonth


def test_the_month_of_a_date_is_the_month_it_falls_in() -> None:
    assert ReportingMonth.of(date(2026, 2, 28)) == ReportingMonth(2026, 2)


def _accepted(month: int) -> bool:
    try:
        ReportingMonth(2026, month)
    except ValueError:
        return False
    return True


def test_only_the_twelve_calendar_months_are_accepted() -> None:
    band = range(-100, 100 + 1)

    accepted = [month for month in band if _accepted(month)]

    assert accepted == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]


def _types_in(hint: object) -> set[object]:
    """Return `hint` and every type it is built from, such as both sides of `|`."""
    if isinstance(hint, TypeAliasType):
        return _types_in(hint.__value__)
    found: set[object] = {hint}
    for argument in get_args(hint):
        found |= _types_in(argument)
    return found


def test_no_contract_record_declares_a_float() -> None:
    records = [
        exported
        for exported in vars(budget.gold).values()
        if isinstance(exported, type) and exported.__module__ == "budget.gold.models"
    ]

    floats = [
        f"{record.__name__}.{field}"
        for record in records
        for field, hint in get_type_hints(record).items()
        if float in _types_in(hint)
    ]

    assert budget.gold.GoldTransaction in records  # the scan found the records
    assert floats == []
