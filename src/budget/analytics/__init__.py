# Copyright 2026 Therkel
"""Household reports from one Gold publication, as `report-contract.md` defines them.

Analytics reads Gold only through `GoldRepository`; it never imports Bronze,
Silver, a parser or `GoldLineageRepository`.
"""

from budget.analytics.overview import monthly_overview, selection_options
from budget.analytics.reports import (
    AccountMonth,
    AccountMonthCoverage,
    AccountMonthStatus,
    CategorySpending,
    InvalidSelectionError,
    MoneyInOut,
    MonthlyOverview,
    Provisional,
    ProvisionalReason,
    ReportContext,
    ReportCoverage,
    ReportPublication,
    SelectableAccount,
    SelectionOptions,
    SelectionRule,
)

__all__ = [
    "AccountMonth",
    "AccountMonthCoverage",
    "AccountMonthStatus",
    "CategorySpending",
    "InvalidSelectionError",
    "MoneyInOut",
    "MonthlyOverview",
    "Provisional",
    "ProvisionalReason",
    "ReportContext",
    "ReportCoverage",
    "ReportPublication",
    "SelectableAccount",
    "SelectionOptions",
    "SelectionRule",
    "monthly_overview",
    "selection_options",
]
