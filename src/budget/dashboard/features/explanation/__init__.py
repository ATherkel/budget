# Copyright 2026 Therkel
"""The explanation page (`/explanation`): one pinned report's trust notes."""

from pathlib import Path
from typing import Annotated

from fastapi import Query, Request, Response
from fastapi.responses import HTMLResponse

from budget.dashboard.addresses import PinnedQuery, answered_url
from budget.dashboard.display.months import month_label
from budget.dashboard.display.text import incomplete_months
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.safe_return import back_url
from budget.dashboard.features.view_state import parse_view_state
from budget.dashboard.reading import read_overview


def _render_explanation(
    dashboard: Dashboard,
    address: PinnedQuery,
    return_to: str | None,
) -> str:
    """Render the explanation page of one pinned report's trust notes."""
    view = parse_view_state(address.mode, address.tab, address.comparison)
    overview_report = read_overview(
        dashboard, address.pin(), address.account, address.month
    )
    page = dashboard.templates.get_template("explanation/explanation.html")
    if isinstance(overview_report, str):
        return page.render(failure=overview_report)
    return page.render(
        overview=overview_report,
        incomplete_months=incomplete_months(overview_report.coverage),
        month_label=month_label(overview_report.context.month),
        report_url=back_url(
            dashboard, return_to, answered_url(overview_report, "/", view)
        ),
    )


def _register(dashboard: Dashboard) -> None:
    """Serve the explanation page at `/explanation` to a reader."""

    @dashboard.app.get("/explanation")
    def explanation(
        request: Request,
        address: Annotated[PinnedQuery, Query()],
        return_to: str | None = None,
    ) -> Response:
        return dashboard.for_reader(
            request,
            lambda: HTMLResponse(_render_explanation(dashboard, address, return_to)),
        )


EXPLANATION = Feature(folder=Path(__file__).parent, register=_register)
