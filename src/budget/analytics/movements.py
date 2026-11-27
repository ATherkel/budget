# Copyright 2026 Therkel
"""The rows behind the monthly overview's summary groups."""

from budget.analytics.measures import SUMMARY_GROUPS, ZERO
from budget.analytics.reports import MoneyInOut, MovementGroup


def movements() -> tuple[MovementGroup, ...]:
    """Return one group per summary group, in card order."""
    return tuple(
        MovementGroup(group, (), ZERO, MoneyInOut(ZERO, ZERO, 0))
        for group in SUMMARY_GROUPS
    )
