# Copyright 2026 Therkel
"""The monthly overview and the selection options of one opened publication.

The caller opens the publication and says whether it is current; analytics
never decides which publication a page reads.
"""

import calendar
from datetime import date

from budget.analytics.measures import figures
from budget.analytics.reports import (
    MonthlyOverview,
    ReportContext,
    ReportPublication,
    SelectionOptions,
)
from budget.analytics.trust import trust
from budget.gold import GoldRepository, ReportingMonth

# Every snapshot row: an account's rows after the selected month still tell
# whether it has a managed period at all.
_EVERY_MONTH = {
    "start_month": ReportingMonth(1, 1),
    "end_month": ReportingMonth(9999, 12),
}


def _report_publication(gold: GoldRepository, *, is_current: bool) -> ReportPublication:
    publication = gold.publication()
    return ReportPublication(
        publication_id=publication.publication_id,
        kind=publication.kind,
        label=publication.label,
        known_at=publication.known_at,
        is_current=is_current,
    )


def monthly_overview(
    gold: GoldRepository, context: ReportContext, *, is_current: bool
) -> MonthlyOverview:
    """Return the monthly overview `context` selects from the publication `gold` reads.

    `is_current` says whether that publication is current; the caller decides.
    """
    accounts = [a for a in gold.accounts() if a.account_id in context.account_ids]
    judged = trust(
        accounts,
        gold.monthly_balances(account_ids=context.account_ids, **_EVERY_MONTH),
        context.month,
        context.reference_date,
    )
    month = context.month
    start = date(month.year, month.month, 1)
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    known = figures(
        gold.transactions(
            start_date=start, end_date=end, account_ids=context.account_ids
        ),
        gold.category_allocations(
            start_date=start, end_date=end, account_ids=context.account_ids
        ),
        gold.categories(),
    )
    return MonthlyOverview(
        context=context,
        publication=_report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        income=known.income,
        expenses=known.expenses,
        net_cash_flow=known.net_cash_flow,
        savings_rate=known.savings_rate,
        categories=known.categories,
        unclassified=known.unclassified,
        adjustments=known.adjustments,
        coverage=judged.coverage,
        provisional=judged.provisional,
    )


def selection_options(
    gold: GoldRepository, reference_date: date, *, is_current: bool
) -> SelectionOptions:
    """Return what a page may select in the publication `gold` reads."""
    raise NotImplementedError
