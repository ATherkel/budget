# Copyright 2026 Therkel
"""Avanceret's Kontrol tab: the trust diagnostics of one selection.

The report includes `checks/checks.html` in place when its tab is Kontrol.
"""

from collections.abc import Collection
from datetime import date
from pathlib import Path

from jinja2.environment import TemplateModule

from budget.analytics import (
    HouseholdReports,
    InvalidSelectionError,
    PublicationUnavailableError,
    ReportContext,
)
from budget.dashboard.display.months import month_label, parse_month
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.checks.display import ChecksView, checks_view
from budget.dashboard.features.errors import failure_fragment
from budget.gold.store import GoldStore


def read_checks(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> ChecksView | TemplateModule:
    """Return Kontrol's lines for a pinned selection, or a failure fragment."""
    publication_id, reference_date = pin
    try:
        selected_month = parse_month(month)
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(accounts),
            month=selected_month,
            reference_date=reference_date,
        )
        with GoldStore(dashboard.profile, read_only=True) as store:
            diagnostics = HouseholdReports(store).diagnostics(context)
    except (InvalidSelectionError, PublicationUnavailableError) as error:
        return failure_fragment(dashboard, error)
    return checks_view(diagnostics, month_label(selected_month))


def _register(_dashboard: Dashboard) -> None:
    """Add no routes: the report renders the tab in place."""


CHECKS = Feature(folder=Path(__file__).parent, register=_register)
