# Copyright 2026 Therkel
"""Public Gold diagnostics for Kontrol."""

from budget.analytics.overview import report_publication, selected_accounts
from budget.analytics.reports import Diagnostics, ReportContext, ReportCoverage
from budget.gold import GoldRepository


def diagnostics(
    gold: GoldRepository,
    context: ReportContext,
    *,
    is_current: bool,
) -> Diagnostics:
    """Return the diagnostics `context` selects from `gold`."""
    accounts = selected_accounts(gold, context)
    return Diagnostics(
        context=context,
        publication=report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        evidence=(),
        coverage=ReportCoverage(status="no_data", account_months=()),
        provisional=None,
        unclassified=None,
        adjustments=None,
        transfers=None,
        reconciliations=(),
    )
