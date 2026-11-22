# Copyright 2026 Therkel
"""The view-state controls: the month, mode and account pickers of a report."""

from pathlib import Path

from budget.dashboard.features import Dashboard, Feature


def register(_dashboard: Dashboard) -> None:
    """Add no routes: the pages that show the controls include them."""


VIEW_STATE = Feature(folder=Path(__file__).parent, register=register)
