# Copyright 2026 Therkel
"""Compare two publications through their public Gold repository interfaces."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from budget.gold.models import (
    ClassificationReviewItem,
    Coverage,
    GoldCategory,
    ReportingMonth,
)
from budget.gold.repository import GoldRepository

_FIRST_DAY = date.min
_LAST_DAY = date.max
_FIRST_MONTH = ReportingMonth(1, 1)
_LAST_MONTH = ReportingMonth(9999, 12)


@dataclass
class _Measures:
    """The measures of one account and month, summed in that account's currency."""

    income: Decimal = Decimal()
    expenses: Decimal = Decimal()
    categories: dict[str, Decimal] = field(default_factory=dict)
    groups: dict[str, Decimal] = field(default_factory=dict)
    unclassified_in: Decimal = Decimal()
    unclassified_out: Decimal = Decimal()
    unclassified_count: int = 0
    coverage: Coverage | None = None


def _measures(
    figures: dict[tuple[ReportingMonth, str], _Measures],
    month: ReportingMonth,
    account_id: str,
) -> _Measures:
    """Return one account-month figure."""
    return figures.setdefault((month, account_id), _Measures())


def _add_category(
    figures: dict[tuple[ReportingMonth, str], _Measures],
    month: ReportingMonth,
    account_id: str,
    category: GoldCategory,
    amount: Decimal,
) -> None:
    """Add one category allocation to its category and group rollups."""
    measures = _measures(figures, month, account_id)
    if category.direction == "income":
        measures.income += amount
    else:
        measures.expenses += amount
    measures.categories[category.category_id] = (
        measures.categories.get(category.category_id, Decimal()) + amount
    )
    measures.groups[category.group_id] = (
        measures.groups.get(category.group_id, Decimal()) + amount
    )


def _add_unknown(
    figures: dict[tuple[ReportingMonth, str], _Measures],
    month: ReportingMonth,
    account_id: str,
    amount: Decimal,
) -> None:
    """Add one unknown transaction to its directional money-in/out totals."""
    measures = _measures(figures, month, account_id)
    measures.unclassified_count += 1
    if amount < 0:
        measures.unclassified_out += amount
    else:
        measures.unclassified_in += amount


def _figures(
    publication: GoldRepository,
) -> tuple[dict[tuple[ReportingMonth, str], _Measures], dict[str, str]]:
    """Read the financial measures and currencies of one publication."""
    accounts = publication.accounts()
    currencies = {account.account_id: account.currency for account in accounts}
    categories = {
        category.category_id: category for category in publication.categories()
    }
    figures: dict[tuple[ReportingMonth, str], _Measures] = {}
    for allocation in publication.category_allocations(
        start_date=_FIRST_DAY, end_date=_LAST_DAY
    ):
        _add_category(
            figures,
            ReportingMonth.of(allocation.transaction_date),
            allocation.account_id,
            categories[allocation.category_id],
            allocation.amount,
        )
    for transaction in publication.transactions(
        start_date=_FIRST_DAY, end_date=_LAST_DAY
    ):
        if transaction.transaction_type == "unknown":
            _add_unknown(
                figures,
                ReportingMonth.of(transaction.transaction_date),
                transaction.account_id,
                transaction.amount,
            )
    for snapshot in publication.monthly_balances(
        start_month=_FIRST_MONTH, end_month=_LAST_MONTH
    ):
        _measures(
            figures, snapshot.month, snapshot.account_id
        ).coverage = snapshot.coverage
    return figures, currencies


def _changed_values(
    before: dict[str, Decimal], after: dict[str, Decimal]
) -> list[tuple[str, Decimal]]:
    """Return sorted values whose totals changed."""
    return [
        (name, after.get(name, Decimal()) - before.get(name, Decimal()))
        for name in sorted(before.keys() | after.keys())
        if before.get(name, Decimal()) != after.get(name, Decimal())
    ]


def _changed(
    key: tuple[ReportingMonth, str],
    before: dict[tuple[ReportingMonth, str], _Measures],
    after: dict[tuple[ReportingMonth, str], _Measures],
) -> bool:
    """Whether an account-month exists on both sides with different measures."""
    return (
        (key in before and key in after and before[key] != after[key])
        or key not in before
        or key not in after
    )


def _money(value: Decimal, currency: str) -> str:
    """Format a signed money delta with its account's currency."""
    return f"{value:+f} {currency}"


def _line(
    key: tuple[ReportingMonth, str],
    before: _Measures,
    after: _Measures,
    currency: str,
) -> str:
    """Format one changed account-month line."""
    month, account_id = key
    changes: list[str] = []
    for label, old, new in (
        ("income", before.income, after.income),
        ("expenses", before.expenses, after.expenses),
    ):
        if old != new:
            changes.append(f"{label} {_money(new - old, currency)}")
    changes.extend(
        f"category {name} {_money(change, currency)}"
        for name, change in _changed_values(before.categories, after.categories)
    )
    changes.extend(
        f"group {name} {_money(change, currency)}"
        for name, change in _changed_values(before.groups, after.groups)
    )
    for label, old, new in (
        ("unclassified in", before.unclassified_in, after.unclassified_in),
        ("unclassified out", before.unclassified_out, after.unclassified_out),
    ):
        if old != new:
            changes.append(f"{label} {_money(new - old, currency)}")
    count_change = after.unclassified_count - before.unclassified_count
    if count_change:
        changes.append(f"unclassified count {count_change:+d}")
    if before.coverage != after.coverage:
        changes.append(
            f"coverage {before.coverage or 'absent'} -> {after.coverage or 'absent'}"
        )
    return f"Changes  {month.year:04d}-{month.month:02d} {account_id}: " + "; ".join(
        changes
    )


def compare_publications(
    previous: GoldRepository,
    current: GoldRepository,
    *,
    previous_reviews: Sequence[ClassificationReviewItem] = (),
    current_reviews: Sequence[ClassificationReviewItem] = (),
) -> tuple[str, ...]:
    """Return terminal lines for the measures that differ between publications."""
    del previous_reviews, current_reviews
    before, previous_currencies = _figures(previous)
    after, current_currencies = _figures(current)
    currencies = {**previous_currencies, **current_currencies}
    return tuple(
        _line(
            key,
            before.get(key, _Measures()),
            after.get(key, _Measures()),
            currencies[key[1]],
        )
        for key in sorted(before.keys() | after.keys())
        if _changed(key, before, after)
    )
