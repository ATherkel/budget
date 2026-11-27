# Copyright 2026 Therkel
"""The explanation page (`/explanation`): one pinned report's trust notes."""

from collections.abc import Collection
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Query, Request, Response
from fastapi.responses import HTMLResponse
from jinja2.environment import TemplateModule

from budget.dashboard.addresses import PinnedQuery, answered_url
from budget.dashboard.display.months import month_label
from budget.dashboard.display.notices import newer_figures
from budget.dashboard.display.text import incomplete_months
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.view_state import ViewState, parse_view_state
from budget.dashboard.reading import read_overview


def _render_explanation(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
    view: ViewState,
) -> str:
    """Render the explanation page of one pinned report's trust notes."""
    overview_report = read_overview(dashboard, pin, accounts, month)
    templates = dashboard.templates
    if isinstance(overview_report, TemplateModule):
        failure = templates.get_template("explanation/explanation_failure.html")
        return failure.render(failure=overview_report)
    page = templates.get_template("explanation/explanation.html")
    label = month_label(overview_report.context.month)
    return page.render(
        heading=f"Om tallene for {label}",
        overview=overview_report,
        notices=newer_figures(overview_report.publication.is_current),
        incomplete_months=incomplete_months(overview_report.coverage),
        month_label=label,
        # The month opens a sentence.
        capitalized_month=label.capitalize(),
        report_url=answered_url(overview_report, "/", view),
    )


def _register(dashboard: Dashboard) -> None:
    """Serve the explanation page at `/explanation` to a reader."""

    @dashboard.app.get("/explanation")
    def explanation(
        request: Request,
        address: Annotated[PinnedQuery, Query()],
    ) -> Response:
        return dashboard.for_reader(
            request,
            lambda: HTMLResponse(
                _render_explanation(
                    dashboard,
                    address.pin(),
                    address.account,
                    address.month,
                    parse_view_state(address.mode, address.tab, address.comparison),
                )
            ),
        )


EXPLANATION = Feature(folder=Path(__file__).parent, register=_register)
