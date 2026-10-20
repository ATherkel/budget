# Copyright 2026 Therkel
"""Household reports from one Gold publication, as `report-contract.md` defines them.

Analytics reads Gold only through `GoldRepository`; it never imports Bronze,
Silver, a parser or `GoldLineageRepository`.
"""

from budget.analytics.household import HouseholdReports
from budget.analytics.overview import monthly_overview, selection_options
from budget.analytics.reports import (
    AccountMonth,
    AccountMonthCoverage,
    AccountMonthStatus,
    CategorySpending,
    InvalidSelectionError,
    MoneyInOut,
    MonthlyOverview,
    NothingPublishedError,
    Provisional,
    ProvisionalReason,
    ReportContext,
    ReportCoverage,
    ReportPublication,
    SelectableAccount,
    SelectionOptions,
    SelectionRule,
)
from budget.gold import PublicationUnavailableError

__all__ = [
    "AccountMonth",
    "AccountMonthCoverage",
    "AccountMonthStatus",
    "CategorySpending",
    "HouseholdReports",
    "InvalidSelectionError",
    "MoneyInOut",
    "MonthlyOverview",
    "NothingPublishedError",
    "Provisional",
    "ProvisionalReason",
    "PublicationUnavailableError",
    "ReportContext",
    "ReportCoverage",
    "ReportPublication",
    "SelectableAccount",
    "SelectionOptions",
    "SelectionRule",
    "monthly_overview",
    "selection_options",
]
