# Copyright 2026 Therkel
"""Avanceret's Kontrol tab: the trust diagnostics of one selection.

The report includes `checks/checks.html` in place when its tab is Kontrol.
"""

from collections.abc import Collection
from datetime import date
from pathlib import Path

from budget.analytics import (
    Diagnostics,
    HouseholdReports,
    InvalidSelectionError,
    PublicationUnavailableError,
    ReportContext,
)
from budget.dashboard.display.months import parse_month
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.errors import failure_fragment
from budget.gold.store import GoldStore


def read_diagnostics(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> Diagnostics | str:
    """Return the diagnostics of a pinned selection, or a failure fragment."""
    publication_id, reference_date = pin
    try:
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(accounts),
            month=parse_month(month),
            reference_date=reference_date,
        )
        with GoldStore(dashboard.profile, read_only=True) as store:
            return HouseholdReports(store).diagnostics(context)
    except (InvalidSelectionError, PublicationUnavailableError) as error:
        return failure_fragment(dashboard, error)


def _register(_dashboard: Dashboard) -> None:
    """Add no routes: the report renders the tab in place."""


CHECKS = Feature(folder=Path(__file__).parent, register=_register)
