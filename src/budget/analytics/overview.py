# Copyright 2026 Therkel
"""The monthly overview and the selection options of one opened publication.

The caller opens the publication and says whether it is current; analytics
never decides which publication a page reads.
"""

import calendar
from collections.abc import Collection, Sequence
from datetime import date

from budget.analytics.measures import UNKNOWN, Figures, figures
from budget.analytics.reports import (
    MonthlyOverview,
    ReportContext,
    ReportPublication,
    SelectableAccount,
    SelectionOptions,
)
from budget.analytics.trust import trust
from budget.gold import GoldRepository, MonthlyBalanceSnapshot, ReportingMonth


def _every_row(
    gold: GoldRepository, account_ids: Collection[str] | None = None
) -> Sequence[MonthlyBalanceSnapshot]:
    """Return every snapshot row of `account_ids`, whatever its month.

    An account's rows after the selected month still tell whether it has a
    managed period at all.
    """
    return gold.monthly_balances(
        start_month=ReportingMonth(1, 1),
        end_month=ReportingMonth(9999, 12),
        account_ids=account_ids,
    )


def _report_publication(gold: GoldRepository, *, is_current: bool) -> ReportPublication:
    publication = gold.publication()
    return ReportPublication(
        publication_id=publication.publication_id,
        kind=publication.kind,
        label=publication.label,
        known_at=publication.known_at,
        is_current=is_current,
    )


def _figures(
    gold: GoldRepository, month: ReportingMonth, account_ids: Collection[str]
) -> Figures:
    """Return the figures of `month`'s transactions on `account_ids`."""
    start = date(month.year, month.month, 1)
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    return figures(
        gold.transactions(start_date=start, end_date=end, account_ids=account_ids),
        gold.category_allocations(
            start_date=start, end_date=end, account_ids=account_ids
        ),
        gold.categories(),
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
        _every_row(gold, context.account_ids),
        context.month,
        context.reference_date,
    )
    known = (
        UNKNOWN
        if judged.coverage.status == "no_data"
        else _figures(gold, context.month, context.account_ids)
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
    reference_month = ReportingMonth.of(reference_date)
    return SelectionOptions(
        publication=_report_publication(gold, is_current=is_current),
        accounts=tuple(
            SelectableAccount(
                account_id=account.account_id,
                display_name=account.display_name,
                account_type=account.account_type,
                ownership_scope=account.ownership_scope,
                currency=account.currency,
            )
            for account in sorted(gold.accounts(), key=lambda a: a.account_id)
        ),
        first_month=min(
            (row.month for row in _every_row(gold)),
            default=reference_month,
        ),
        last_month=reference_month,
    )
