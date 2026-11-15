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
from budget.analytics.trust import trust_over
from budget.gold import GoldCategory, GoldRepository, ReportingMonth


def _first_day(month: ReportingMonth) -> date:
    return date(month.year, month.month, 1)


def _last_day(month: ReportingMonth) -> date:
    return date(
        month.year, month.month, calendar.monthrange(month.year, month.month)[1]
    )


def _scope_months(
    context: ReportContext, scope: DetailScope
) -> tuple[ReportingMonth, ReportingMonth]:
    """Return the first and last month of `scope`: January through the month."""
    first = (
        ReportingMonth(context.month.year, 1)
        if scope == "year_to_date"
        else context.month
    )
    return first, context.month


def _subject_categories(
    gold: GoldRepository, subject: DetailSubject
) -> list[GoldCategory]:
    """Return the expense categories `subject` names."""
    return [
        category
        for category in gold.categories()
        if category.direction == "expense"
        and (category.category_id if subject.kind == "category" else category.group_id)
        == subject.id
    ]


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
    categories = {c.category_id: c for c in _subject_categories(gold, subject)}
    first_month, last_month = _scope_months(context, scope)
    window = {
        "start_date": _first_day(first_month),
        "end_date": _last_day(last_month),
        "account_ids": context.account_ids,
    }
    names = {a.account_id: a.display_name for a in accounts}
    transactions = {t.transaction_id: t for t in gold.transactions(**window)}
    # Newest first: by date, then account, then booking sequence, descending.
    entries = sorted(
        (a for a in gold.category_allocations(**window) if a.category_id in categories),
        key=lambda a: (
            a.transaction_date,
            a.account_id,
            transactions[a.transaction_id].account_sequence,
        ),
        reverse=True,
    )
    rows = tuple(
        SpendingDetailRow(
            transaction_date=a.transaction_date,
            description=transactions[a.transaction_id].description,
            account_id=a.account_id,
            account_display_name=names[a.account_id],
            category_id=a.category_id,
            category_name=categories[a.category_id].name,
            spending=-a.amount,
        )
        for a in entries
    )
    judged = trust_over(
        accounts,
        _every_row(gold, context.account_ids),
        first_month,
        last_month,
        context.reference_date,
    )
    no_data = judged.coverage.status == "no_data"
    anchor = next(iter(categories.values()))
    is_group = subject.kind == "group"
    return SpendingDetail(
        context=context,
        subject=subject,
        scope=scope,
        publication=_report_publication(gold, is_current=is_current),
        currency=accounts[0].currency,
        name=anchor.group_name if is_group else anchor.name,
        group_id=anchor.group_id,
        group_name=anchor.group_name,
        first_month=first_month,
        last_month=last_month,
        spending=None if no_data else sum((row.spending for row in rows), ZERO),
        rows=() if no_data else rows,
        coverage=judged.coverage,
        provisional=judged.provisional,
    )
