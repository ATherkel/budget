# Copyright 2026 Therkel
"""The view-state controls: the month, mode and account pickers of a report.

The view state is the presentation a report is shown in: its mode, tab and
comparison, carried beside the pinned report context in every address.
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from jinja2 import Environment

from budget.analytics import SelectionOptions
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.view_state.display import (
    account_shortcuts,
    month_choices,
)

type DashboardMode = Literal["simple", "advanced"]
type DashboardTab = Literal["overview", "details", "checks"]
type ComparisonMode = Literal["amounts"]


@dataclass(frozen=True)
class ViewState:
    """Presentation state carried beside the pinned report context."""

    mode: DashboardMode = "simple"
    tab: DashboardTab = "overview"
    comparison: ComparisonMode = "amounts"


DEFAULT_VIEW = ViewState()


def view_mode(value: str | None) -> DashboardMode:
    """Return the supported mode named by `value`, defaulting to Enkel."""
    return "advanced" if value == "advanced" else "simple"


def _tab(value: str | None) -> DashboardTab:
    """Return a supported tab, defaulting a malformed address to Overblik."""
    if value == "details" or value == "checks":
        return value
    return "overview"


def _comparison(_value: str | None) -> ComparisonMode:
    """Return the only delivered comparison."""
    return "amounts"


def parse_view_state(
    mode: str | None,
    tab: str | None = None,
    comparison: str | None = None,
) -> ViewState:
    """Return the delivered presentation state a mode and address select."""
    normalized_mode = view_mode(mode)
    return ViewState(
        mode=normalized_mode,
        tab=_tab(tab) if normalized_mode == "advanced" else "overview",
        comparison=_comparison(comparison),
    )


def view_state_controls(templates: Environment, view: ViewState) -> str:
    """Render the out-of-band controls every report response keeps current."""
    return templates.get_template("view_state/controls.html").render(
        mode=view.mode,
        tab=view.tab,
        comparison=view.comparison,
    )


@dataclass(frozen=True)
class Selection:
    """What the selection form shows as chosen, under one pinned publication."""

    publication_id: int
    reference_date: date
    accounts: Collection[str]
    month: str
    view: ViewState


def selection_form(
    options: SelectionOptions,
    chosen: Selection,
    selecting: Callable[[Collection[str]], str],
) -> dict[str, object]:
    """Return what `view_state/selection.html` renders from.

    `selecting` returns the page's address with the given accounts selected.
    """
    return {
        "publication_id": chosen.publication_id,
        "reference_date": chosen.reference_date.isoformat(),
        "accounts": options.accounts,
        "selected_accounts": chosen.accounts,
        "months": month_choices(options.first_month, options.last_month),
        "selected_month": chosen.month,
        "shortcuts": account_shortcuts(
            [account.account_id for account in options.accounts], selecting
        ),
        "mode": chosen.view.mode,
        "tab": chosen.view.tab,
        "comparison": chosen.view.comparison,
    }


def register(_dashboard: Dashboard) -> None:
    """Add no routes: the pages that show the controls include them."""


VIEW_STATE = Feature(folder=Path(__file__).parent, register=register)
