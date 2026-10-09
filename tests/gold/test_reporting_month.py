# Copyright 2026 Therkel
"""`ReportingMonth`, the contract's calendar month (`gold-contract.md`)."""

from datetime import date

from budget.gold import ReportingMonth


def test_the_month_of_a_date_is_the_month_it_falls_in() -> None:
    assert ReportingMonth.of(date(2026, 2, 28)) == ReportingMonth(2026, 2)
