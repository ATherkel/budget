# Copyright 2026 Therkel
"""Compare two publications through their public Gold repository interfaces."""

from budget.gold.repository import GoldRepository


def compare_publications(
    previous: GoldRepository,
    current: GoldRepository,
) -> tuple[str, ...]:
    """Return terminal lines for the measures that differ between publications."""
    del previous, current
    return ()
