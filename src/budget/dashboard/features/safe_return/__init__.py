# Copyright 2026 Therkel
"""Safe return: the explanation page links back to the page the reader came from."""

from pathlib import Path
from urllib.parse import urlsplit

from budget.dashboard.features import Dashboard, Feature


def back_url(dashboard: Dashboard, return_to: str | None, fallback: str) -> str:
    """Return where the explanation page links back to.

    That is `return_to` while this feature is registered, else `fallback`.
    """
    if not getattr(dashboard.app.state, "safe_return", False) or return_to is None:
        return fallback
    return return_to if _is_own_page(return_to) else fallback


# The reader's pages a back link may name: none outside the dashboard.
_OWN_PAGES = frozenset({"/", "/category"})


def _is_own_page(address: str) -> bool:
    """Whether `address` is one of the dashboard's own pages, as a browser reads it.

    Browsers drop control characters and read a backslash as a slash, so an
    address holding either could leave the site, and none is accepted.
    """
    if any(character < " " or character in "\\\x7f" for character in address):
        return False
    parts = urlsplit(address)
    return not parts.scheme and not parts.netloc and parts.path in _OWN_PAGES


def _register(dashboard: Dashboard) -> None:
    """Add no routes: mark the dashboard as honouring `return_to`."""
    dashboard.app.state.safe_return = True


SAFE_RETURN = Feature(folder=Path(__file__).parent, register=_register)
