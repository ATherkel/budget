# Copyright 2026 Therkel
"""Reading the overview a pinned selection asks for, which several pages show."""

from collections.abc import Collection
from datetime import date

from budget.analytics import (
    HouseholdReports,
    InvalidSelectionError,
    MonthlyOverview,
    PublicationUnavailableError,
    ReportContext,
)
from budget.dashboard.display.months import parse_month
from budget.dashboard.display.text import selection_problems
from budget.dashboard.features import Dashboard
from budget.gold.store import GoldStore


def read_overview(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> MonthlyOverview | str:
    """Return the overview a selection asks for, or a fragment saying why not.

    The pinned context is used exactly as the page sent it: never re-resolved.
    """
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
            return HouseholdReports(store).monthly_overview(context)
    except InvalidSelectionError as error:
        # A failure is shown, and echoes no context the page could render.
        return dashboard.templates.get_template("invalid_selection.html").render(
            problems=selection_problems(error)
        )
    except PublicationUnavailableError:
        return dashboard.templates.get_template("unavailable.html").render()
