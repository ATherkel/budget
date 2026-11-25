# Copyright 2026 Therkel
"""Avanceret's Kontrol tab: the trust diagnostics of one selection.

The report includes `checks/checks.html` in place when its tab is Kontrol.
"""

from pathlib import Path

from budget.dashboard.features import Dashboard, Feature


def _register(_dashboard: Dashboard) -> None:
    """Add no routes: the report renders the tab in place."""


CHECKS = Feature(folder=Path(__file__).parent, register=_register)
