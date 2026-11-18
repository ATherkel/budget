# Copyright 2026 Therkel
"""Account activity and its public Transfer evidence."""

from budget.analytics.overview import report_publication, selected_accounts
from budget.analytics.reports import (
    AccountActivity,
    ReportContext,
    ReportCoverage,
)
from budget.gold import GoldRepository


def account_activity(
    gold: GoldRepository,
    context: ReportContext,
    *,
    is_current: bool,
) -> AccountActivity:
    """Return the account activity `context` selects from `gold`."""
    accounts = selected_accounts(gold, context)
    return AccountActivity(
        context=context,
        publication=report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        accounts=(),
        coverage=ReportCoverage(status="no_data", account_months=()),
        provisional=None,
    )
