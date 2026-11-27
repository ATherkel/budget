# Copyright 2026 Therkel
"""The `sort` application operation: unknown transactions, one group at a time."""

from budget.profiles import Profile


def sort_unknowns(profile: Profile) -> None:
    """Hold the sorting conversation over the current publication's unknowns."""
