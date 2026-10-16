# Copyright 2026 Therkel
"""The monthly overview's figures, as `analytics-layer.md` defines its measures.

Income and Expenses are summed over transactions and category spending over
allocations; the two are never added together (ADR-008).
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from budget.analytics.reports import CategorySpending, MoneyInOut
from budget.gold import (
    CategoryDirection,
    GoldCategory,
    GoldCategoryAllocation,
    GoldTransaction,
    TransactionType,
)

# DKK, the only first-release currency, has two minor-unit places.
ZERO = Decimal("0.00")


@dataclass(frozen=True)
class Figures:
    """Every money figure of one month's overview; all null without evidence."""

    income: Decimal | None
    expenses: Decimal | None
    net_cash_flow: Decimal | None
    savings_rate: Decimal | None
    categories: tuple[CategorySpending, ...]
    unclassified: MoneyInOut | None
    adjustments: MoneyInOut | None


# With no evidence a figure is unknown, never zero (report-contract.md).
UNKNOWN = Figures(
    income=None,
    expenses=None,
    net_cash_flow=None,
    savings_rate=None,
    categories=(),
    unclassified=None,
    adjustments=None,
)


def _total(amounts: Iterable[Decimal]) -> Decimal:
    return sum(amounts, ZERO)


def _money_in_out(
    transactions: Sequence[GoldTransaction], transaction_type: TransactionType
) -> MoneyInOut:
    """Money in and money out of one transaction type, never netted."""
    amounts = [t.amount for t in transactions if t.transaction_type == transaction_type]
    return MoneyInOut(
        money_in=_total(a for a in amounts if a > 0),
        money_out=_total(a for a in amounts if a < 0),
        count=len(amounts),
    )


def _measure(
    transaction: GoldTransaction,
    refund_directions: dict[str, CategoryDirection],
) -> CategoryDirection | None:
    """Return the measure a transaction counts toward; a Refund takes its category's."""
    if transaction.transaction_type == "refund":
        return refund_directions[transaction.transaction_id]
    if transaction.transaction_type in {"income", "expense"}:
        return "income" if transaction.transaction_type == "income" else "expense"
    return None


def _category_spending(
    allocations: Sequence[GoldCategoryAllocation],
    categories: dict[str, GoldCategory],
) -> tuple[CategorySpending, ...]:
    """Each expense Category's net spending, largest first, then by `category_id`."""
    spent: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for allocation in allocations:
        if categories[allocation.category_id].direction == "expense":
            spent[allocation.category_id] -= allocation.amount
    rows = (
        CategorySpending(
            category_id=category_id,
            name=categories[category_id].name,
            group_id=categories[category_id].group_id,
            group_name=categories[category_id].group_name,
            spending=spending,
        )
        for category_id, spending in spent.items()
    )
    return tuple(sorted(rows, key=lambda row: (-row.spending, row.category_id)))


def figures(
    transactions: Sequence[GoldTransaction],
    allocations: Sequence[GoldCategoryAllocation],
    categories: Sequence[GoldCategory],
) -> Figures:
    """Return the figures of one month's transactions and their allocations."""
    by_id = {category.category_id: category for category in categories}
    # Gold contract invariant 7: a Refund's allocation carries the category of
    # the movement it reverses, so the category's direction is the Refund's.
    refund_directions = {
        allocation.transaction_id: by_id[allocation.category_id].direction
        for allocation in allocations
    }
    measured = [(_measure(t, refund_directions), t.amount) for t in transactions]
    income = _total(amount for measure, amount in measured if measure == "income")
    expenses = ZERO - _total(
        amount for measure, amount in measured if measure == "expense"
    )
    net_cash_flow = income - expenses
    return Figures(
        income=income,
        expenses=expenses,
        net_cash_flow=net_cash_flow,
        savings_rate=net_cash_flow / income if income > 0 else None,
        categories=_category_spending(allocations, by_id),
        unclassified=_money_in_out(transactions, "unknown"),
        adjustments=_money_in_out(transactions, "adjustment"),
    )
