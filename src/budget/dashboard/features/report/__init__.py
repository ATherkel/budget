# Copyright 2026 Therkel
"""The report (`/report`): one selection's figures, swapped into the overview."""

from pathlib import Path

from budget.dashboard.features import Dashboard, Feature


def _register(_dashboard: Dashboard) -> None:
    """Serve nothing yet."""


REPORT = Feature(folder=Path(__file__).parent, register=_register)
