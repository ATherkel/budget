# Copyright 2026 Therkel
"""The login page (`/login`) and logging out (`/logout`)."""

from pathlib import Path

from budget.dashboard.features import Dashboard, Feature


def _register(dashboard: Dashboard) -> None:
    """Serve logging in at `/login` and logging out at `/logout`."""


LOGIN = Feature(folder=Path(__file__).parent, register=_register)
