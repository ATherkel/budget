# Copyright 2026 Therkel
"""The entries behind one Category's or group's overview figure."""

import calendar
from datetime import date

from budget.analytics.measures import ZERO
from budget.analytics.overview import (
    _every_row,
    _report_publication,
    _selected_accounts,
)
from budget.analytics.reports import (
    DetailScope,
    DetailSubject,
    ReportContext,
    SpendingDetail,
    SpendingDetailRow,
)
from budget.analytics.trust import trust
from budget.gold import GoldRepository, ReportingMonth


def _first_day(month: ReportingMonth) -> date:
    return date(month.year, month.month, 1)


def _last_day(month: ReportingMonth) -> date:
    return date(
        month.year, month.month, calendar.monthrange(month.year, month.month)[1]
    )


def spending_detail(
    gold: GoldRepository,
    context: ReportContext,
    subject: DetailSubject,
    scope: DetailScope,
    *,
    is_current: bool,
) -> SpendingDetail:
    """Return the entries behind `subject`'s figure in `scope`."""
    accounts = _selected_accounts(gold, context)
    category = next(c for c in gold.categories() if c.category_id == subject.id)
    allocations = gold.category_allocations(
        start_date=_first_day(context.month),
        end_date=_last_day(context.month),
        account_ids=context.account_ids,
    )
    names = {a.account_id: a.display_name for a in accounts}
    transactions = {
        t.transaction_id: t
        for t in gold.transactions(
            start_date=_first_day(context.month),
            end_date=_last_day(context.month),
            account_ids=context.account_ids,
        )
    }
    rows = tuple(
        SpendingDetailRow(
            transaction_date=a.transaction_date,
            description=transactions[a.transaction_id].description,
            account_id=a.account_id,
            account_display_name=names[a.account_id],
            category_id=category.category_id,
            category_name=category.name,
            spending=-a.amount,
        )
        for a in allocations
        if a.category_id == category.category_id
    )
    judged = trust(
        accounts,
        _every_row(gold, context.account_ids),
        context.month,
        context.reference_date,
    )
    return SpendingDetail(
        context=context,
        subject=subject,
        scope=scope,
        publication=_report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        name=category.name,
        group_id=category.group_id,
        group_name=category.group_name,
        first_month=context.month,
        last_month=context.month,
        spending=sum((row.spending for row in rows), ZERO),
        rows=tuple(sorted(rows, key=lambda row: row.transaction_date, reverse=True)),
        coverage=judged.coverage,
        provisional=judged.provisional,
    )
