# Copyright 2026 Therkel
"""Household reports from one Gold publication, as `report-contract.md` defines them.

Analytics reads Gold only through `GoldRepository`; it never imports Bronze,
Silver, a parser or `GoldLineageRepository`.
"""

from budget.analytics.activity import account_activity
from budget.analytics.household import (
    HouseholdReports,
    NothingPublishedError,
    PublicationUnavailableError,
)
from budget.analytics.overview import monthly_overview, selection_options
from budget.analytics.reports import (
    AccountActivity,
    AccountActivitySnapshot,
    AccountMonth,
    AccountMonthCoverage,
    AccountMonthStatus,
    ActivityRow,
    BankBalanceObservation,
    CategorySpending,
    DetailScope,
    DetailSubject,
    InvalidSelectionError,
    MoneyInOut,
    MonthlyBalanceObservation,
    MonthlyOverview,
    Provisional,
    ProvisionalReason,
    ReportContext,
    ReportCoverage,
    ReportPublication,
    SelectableAccount,
    SelectionOptions,
    SelectionRule,
    SpendingDetail,
    SpendingDetailRow,
    TransferPairing,
)

__all__ = [
    "AccountActivity",
    "AccountActivitySnapshot",
    "AccountMonth",
    "AccountMonthCoverage",
    "AccountMonthStatus",
    "ActivityRow",
    "BankBalanceObservation",
    "CategorySpending",
    "DetailScope",
    "DetailSubject",
    "HouseholdReports",
    "InvalidSelectionError",
    "MoneyInOut",
    "MonthlyBalanceObservation",
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
    "SpendingDetail",
    "SpendingDetailRow",
    "TransferPairing",
    "account_activity",
    "monthly_overview",
    "selection_options",
]
