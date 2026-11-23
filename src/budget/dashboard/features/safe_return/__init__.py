# Copyright 2026 Therkel
"""Safe return: the explanation page links back to the page the reader came from."""

from pathlib import Path

from budget.dashboard.features import Dashboard, Feature


def back_url(dashboard: Dashboard, return_to: str | None, fallback: str) -> str:
    """Return where the explanation page links back to.

    That is `return_to` while this feature is registered, else `fallback`.
    """
    if not getattr(dashboard.app.state, "safe_return", False):
        return fallback
    return return_to or fallback


def _register(dashboard: Dashboard) -> None:
    """Add no routes: mark the dashboard as honouring `return_to`."""
    dashboard.app.state.safe_return = True


SAFE_RETURN = Feature(folder=Path(__file__).parent, register=_register)
