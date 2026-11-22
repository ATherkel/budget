# Copyright 2026 Therkel
"""The overview page (`/`): the selection form beside the report it selects."""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from budget.analytics import (
    HouseholdReports,
    NothingPublishedError,
    PublicationUnavailableError,
)
from budget.dashboard.addresses import PinnedAddress, ReportRequest, pinned_url
from budget.dashboard.display.months import copenhagen_date, month_value
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.view_state import (
    Selection,
    ViewState,
    parse_view_state,
    selection_form,
)
from budget.gold import ReportingMonth
from budget.gold.store import GoldStore

# Renders the report fragment one request selects, or why it cannot be shown.
type ReportRenderer = Callable[[Dashboard, ReportRequest], str]


@dataclass(frozen=True)
class OverviewRequest:
    """A complete overview-page request, fresh or pinned."""

    pin: tuple[int, date] | None
    accounts: tuple[str, ...] | None
    month: str | None
    view: ViewState


class OverviewAddress(BaseModel):
    """Query parameters of a fresh or restored overview."""

    publication: int | None = None
    reference_date: date | None = None
    month: str | None = None
    account: list[str] = []
    mode: str = "simple"
    tab: str = "overview"
    comparison: str = "amounts"

    def asked(self) -> OverviewRequest:
        """Return the page request without resolving a fresh pin."""
        pinned = self.publication is not None and self.reference_date is not None
        return OverviewRequest(
            pin=(
                None
                if self.publication is None or self.reference_date is None
                else (self.publication, self.reference_date)
            ),
            accounts=tuple(self.account) if pinned else None,
            month=self.month,
            view=parse_view_state(self.mode, self.tab, self.comparison),
        )


def _render_overview(
    dashboard: Dashboard,
    requested: OverviewRequest,
    render_report: ReportRenderer,
) -> str:
    """Render the overview page.

    A pinned page keeps its publication, reference date and selection. A fresh
    visit resolves the current publication and today's Copenhagen date, with
    every account and this month selected.
    """
    # A pinned address without accounts is an empty selection, not a fresh visit.
    fresh = requested.pin is None
    pin = requested.pin
    templates = dashboard.templates
    with GoldStore(dashboard.profile, read_only=True) as store:
        reports = HouseholdReports(store)
        if pin is None:
            try:
                publication_id = reports.current_publication().publication_id
            except NothingPublishedError:
                page = templates.get_template("overview/nothing_published.html")
                return page.render()
            pin = (publication_id, copenhagen_date(dashboard.clock()))
        publication_id, reference_date = pin
        try:
            options = reports.selection_options(publication_id, reference_date)
        except PublicationUnavailableError:
            # Offered, never substituted: the reader chooses the current figures.
            return templates.get_template("overview/unavailable_page.html").render()
    selected_accounts = (
        {account.account_id for account in options.accounts}
        if fresh
        else set(requested.accounts or ())
    )
    selected_month = requested.month or month_value(ReportingMonth.of(reference_date))
    # The page carries its own report, so back, forward and a page without
    # scripts show what the selection's report says.
    report = render_report(
        dashboard,
        ReportRequest(
            pin,
            tuple(selected_accounts),
            selected_month,
            requested.view,
            requested.view.mode,
        ),
    )

    def pinned_with(accounts: Collection[str]) -> str:
        """Return this page's address with `accounts` selected instead."""
        return pinned_url(
            PinnedAddress(
                publication_id, reference_date, tuple(accounts), selected_month
            ),
            view=requested.view,
        )

    chosen = Selection(
        publication_id,
        reference_date,
        selected_accounts,
        selected_month,
        requested.view,
    )
    return templates.get_template("overview/overview.html").render(
        canonical_url=pinned_with(selected_accounts),
        report=report,
        **selection_form(options, chosen, pinned_with),
    )


def overview_feature(render_report: ReportRenderer) -> Feature:
    """Return the overview, which embeds the report `render_report` renders."""

    def register(dashboard: Dashboard) -> None:
        """Serve the overview at `/` to a logged-in reader."""

        @dashboard.app.get("/")
        def overview(
            request: Request,
            address: Annotated[OverviewAddress, Query()],
        ) -> Response:
            return dashboard.for_reader(
                request,
                lambda: HTMLResponse(
                    _render_overview(dashboard, address.asked(), render_report)
                ),
            )

    return Feature(folder=Path(__file__).parent, register=register)
