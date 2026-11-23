# Copyright 2026 Therkel
"""Safe return: the explanation page links back to the page the reader came from."""

from pathlib import Path

from budget.dashboard.features import Dashboard, Feature


def back_url(return_to: str | None, fallback: str) -> str:
    """Return where the explanation page links back to."""
    return return_to or fallback


def _register(_dashboard: Dashboard) -> None:
    """Add no routes."""


SAFE_RETURN = Feature(folder=Path(__file__).parent, register=_register)
