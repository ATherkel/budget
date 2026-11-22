# Copyright 2026 Therkel
"""The Danish words and sentences the dashboard's pages show their reader."""

from datetime import date

from budget.dashboard.display.months import danish_date


def test_a_date_reads_day_month_and_year_with_points() -> None:
    assert danish_date(date(2026, 2, 3)) == "03.02.2026"
