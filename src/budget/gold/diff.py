# Copyright 2026 Therkel
"""Compare two publications through their public Gold repository interfaces."""

from collections import Counter
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


@dataclass(frozen=True)
class _LineContext:
    """Account currency and category/group directions for one diff line."""

    currency: str
    categories: dict[str, str]
    groups: dict[str, str]


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
) -> tuple[
    dict[tuple[ReportingMonth, str], _Measures],
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
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
    return (
        figures,
        currencies,
        {category: value.direction for category, value in categories.items()},
        {category.group_id: category.direction for category in categories.values()},
    )


def _changed_values(
    before: dict[str, Decimal],
    after: dict[str, Decimal],
    directions: dict[str, str],
) -> list[tuple[str, Decimal]]:
    """Return sorted values whose totals changed."""
    return [
        (
            name,
            _directed_change(
                before.get(name, Decimal()),
                after.get(name, Decimal()),
                directions[name],
            ),
        )
        for name in sorted(before.keys() | after.keys())
        if before.get(name, Decimal()) != after.get(name, Decimal())
    ]


def _directed_change(before: Decimal, after: Decimal, direction: str) -> Decimal:
    """Return a change in spending magnitude, or in signed income."""
    return before - after if direction == "expense" else after - before


def _money(value: Decimal, currency: str) -> str:
    """Format a signed money delta with its account's currency."""
    return f"{value:+f} {currency}"


def _line(
    key: tuple[ReportingMonth, str],
    before: _Measures,
    after: _Measures,
    context: _LineContext,
) -> str | None:
    """Format one changed account-month line."""
    month, account_id = key
    changes: list[str] = []
    if before.income != after.income:
        changes.append(
            f"income {_money(after.income - before.income, context.currency)}"
        )
    if before.expenses != after.expenses:
        changes.append(
            f"expenses {_money(before.expenses - after.expenses, context.currency)}"
        )
    changes.extend(
        f"category {name} {_money(change, context.currency)}"
        for name, change in _changed_values(
            before.categories, after.categories, context.categories
        )
    )
    changes.extend(
        f"group {name} {_money(change, context.currency)}"
        for name, change in _changed_values(before.groups, after.groups, context.groups)
    )
    for label, old, new in (
        ("unclassified in", before.unclassified_in, after.unclassified_in),
        ("unclassified out", before.unclassified_out, after.unclassified_out),
    ):
        if old != new:
            changes.append(f"{label} {_money(new - old, context.currency)}")
    count_change = after.unclassified_count - before.unclassified_count
    if count_change:
        changes.append(f"unclassified count {count_change:+d}")
    if before.coverage != after.coverage:
        changes.append(
            f"coverage {before.coverage or 'absent'} -> {after.coverage or 'absent'}"
        )
    if not changes:
        return None
    return f"Changes  {month.year:04d}-{month.month:02d} {account_id}: " + "; ".join(
        changes
    )


def _reviews(
    previous: Sequence[ClassificationReviewItem],
    current: Sequence[ClassificationReviewItem],
) -> str | None:
    """Summarize review item identity sets that appeared or disappeared."""
    before = {item.review_item_id: item.kind for item in previous}
    after = {item.review_item_id: item.kind for item in current}
    opened = Counter(after[item_id] for item_id in after.keys() - before.keys())
    closed = Counter(before[item_id] for item_id in before.keys() - after.keys())
    changes = [f"{opened[kind]} {kind} opened" for kind in sorted(opened)] + [
        f"{closed[kind]} {kind} closed" for kind in sorted(closed)
    ]
    return None if not changes else "Review  " + "; ".join(changes)


def compare_publications(
    previous: GoldRepository,
    current: GoldRepository,
    *,
    previous_reviews: Sequence[ClassificationReviewItem] = (),
    current_reviews: Sequence[ClassificationReviewItem] = (),
) -> tuple[str, ...]:
    """Return terminal lines for the measures that differ between publications."""
    before, previous_currencies, previous_categories, previous_groups = _figures(
        previous
    )
    after, current_currencies, current_categories, current_groups = _figures(current)
    currencies = {**previous_currencies, **current_currencies}
    category_directions = {**previous_categories, **current_categories}
    group_directions = {**previous_groups, **current_groups}
    lines = [
        line
        for key in sorted(before.keys() | after.keys())
        if (
            line := _line(
                key,
                before.get(key, _Measures()),
                after.get(key, _Measures()),
                _LineContext(
                    currencies[key[1]],
                    category_directions,
                    group_directions,
                ),
            )
        )
        is not None
    ]
    reviews = _reviews(previous_reviews, current_reviews)
    if reviews is not None:
        lines.append(reviews)
    return tuple(lines)
