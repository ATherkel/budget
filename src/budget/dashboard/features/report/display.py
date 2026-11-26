# Copyright 2026 Therkel
"""What the report prints, prepared so its templates only loop and print."""

from decimal import Decimal

from budget.analytics import MoneyInOut


def unclassified_amounts(
    unclassified: MoneyInOut | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Return the unclassified money in and out; both unknown without figures."""
    if unclassified is None:
        return None, None
    return unclassified.money_in, unclassified.money_out
