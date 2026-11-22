# Copyright 2026 Therkel
"""The view-state controls: the month, mode and account pickers of a report.

The view state is the presentation a report is shown in: its mode, tab and
comparison, carried beside the pinned report context in every address.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from jinja2 import Environment

from budget.dashboard.features import Dashboard, Feature

type DashboardMode = Literal["simple", "advanced"]
type DashboardTab = Literal["overview", "details"]
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
    return "details" if value == "details" else "overview"


def _comparison(_value: str | None) -> ComparisonMode:
    """Return the only delivered comparison."""
    return "amounts"


def view_state(
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


def register(_dashboard: Dashboard) -> None:
    """Add no routes: the pages that show the controls include them."""


VIEW_STATE = Feature(folder=Path(__file__).parent, register=register)
