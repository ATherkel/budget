# Copyright 2026 Therkel
"""Household reports from one Gold publication, as `report-contract.md` defines them.

Analytics reads Gold only through `GoldRepository`; it never imports Bronze,
Silver, a parser or `GoldLineageRepository`.
"""

from budget.analytics.diagnostics import diagnostics
from budget.analytics.household import (
    HouseholdReports,
    NothingPublishedError,
    PublicationUnavailableError,
)
from budget.analytics.overview import monthly_overview, selection_options
from budget.analytics.reports import (
    AccountEvidence,
    AccountMonth,
    AccountMonthCoverage,
    AccountMonthStatus,
    CategorySpending,
    DetailScope,
    DetailSubject,
    Diagnostics,
    InvalidSelectionError,
    MoneyInOut,
    MonthlyOverview,
    Provisional,
    ProvisionalReason,
    Reconciliation,
    ReportContext,
    ReportCoverage,
    ReportPublication,
    SelectableAccount,
    SelectableOwner,
    SelectionOptions,
    SelectionRule,
    SpendingDetail,
    SpendingDetailRow,
    TransferSummary,
)

__all__ = [
    "AccountEvidence",
    "AccountMonth",
    "AccountMonthCoverage",
    "AccountMonthStatus",
    "CategorySpending",
    "DetailScope",
    "DetailSubject",
    "Diagnostics",
    "HouseholdReports",
    "InvalidSelectionError",
    "MoneyInOut",
    "MonthlyOverview",
    "NothingPublishedError",
    "Provisional",
    "ProvisionalReason",
    "PublicationUnavailableError",
    "Reconciliation",
    "ReportContext",
    "ReportCoverage",
    "ReportPublication",
    "SelectableAccount",
    "SelectableOwner",
    "SelectionOptions",
    "SelectionRule",
    "SpendingDetail",
    "SpendingDetailRow",
    "TransferSummary",
    "diagnostics",
    "monthly_overview",
    "selection_options",
]
