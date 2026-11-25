# Copyright 2026 Therkel
"""Kontrol's lines, built from diagnostics without a dashboard.

Covers the cases the worked example cannot publish; `test_checks.py` drives
the rest through the dashboard.
"""

from dataclasses import replace
from datetime import date

from budget.analytics import (
    AccountMonthCoverage,
    ReportContext,
    ReportCoverage,
    diagnostics,
)
from budget.dashboard.features.checks.display import checks_view
from budget.gold import GoldResult, ReportingMonth
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

MARCH = ReportingMonth(2026, 3)
MARCH_REPORT = diagnostics(
    GoldResult(PUBLICATION, RECORDS),
    ReportContext(
        publication_id=1,
        account_ids=frozenset({CURRENT, SAVINGS}),
        month=MARCH,
        reference_date=date(2026, 5, 14),
    ),
    is_current=True,
)


def test_a_month_outside_an_accounts_history_is_not_listed_as_incomplete() -> None:
    coverage = ReportCoverage(
        "partial",
        (
            AccountMonthCoverage(CURRENT, "Joint current", MARCH, "no_data"),
            AccountMonthCoverage(SAVINGS, "Joint savings", MARCH, "outside_history"),
        ),
    )
    outside_only = ReportCoverage(
        "no_data",
        (AccountMonthCoverage(SAVINGS, "Joint savings", MARCH, "outside_history"),),
    )

    assert (
        checks_view(replace(MARCH_REPORT, coverage=coverage), "marts 2026").incomplete,
        checks_view(
            replace(MARCH_REPORT, coverage=outside_only), "marts 2026"
        ).incomplete,
    ) == (
        ["Joint current, marts 2026: ingen data."],
        ["Ingen valgte kontomåneder mangler dækning."],
    )
