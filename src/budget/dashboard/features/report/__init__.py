# Copyright 2026 Therkel
"""The report (`/report`): one selection's figures, swapped into the overview."""

from collections.abc import Collection
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Query, Request, Response
from fastapi.responses import HTMLResponse
from jinja2.environment import TemplateModule

from budget.analytics import (
    AccountActivity,
    HouseholdReports,
    InvalidSelectionError,
    PublicationUnavailableError,
    ReportContext,
)
from budget.dashboard.addresses import (
    PinnedAddress,
    PinnedQuery,
    ReportRequest,
    answered_address,
    answered_url,
    detail_url,
    pinned_url,
)
from budget.dashboard.display.links import switch_links
from budget.dashboard.display.months import month_label, month_value, parse_month
from budget.dashboard.display.text import incomplete_months
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.checks import read_checks
from budget.dashboard.features.errors import failure_fragment
from budget.dashboard.features.report.display import (
    account_rows,
    overview_notices,
    report_notices,
    tab_template,
    unclassified_amounts,
)
from budget.dashboard.features.view_state import (
    ViewState,
    parse_view_state,
    view_mode,
    view_state_controls,
)
from budget.dashboard.reading import read_overview
from budget.gold.store import GoldStore

# The advanced mode's tabs, in the order the report shows them.
_TABS = (("overview", "Overblik"), ("details", "Detaljer"), ("checks", "Kontrol"))


class ReportAddress(PinnedQuery):
    """The query string of one in-place report request and its prior mode."""

    active_mode: str | None = None

    def asked(self) -> ReportRequest:
        """Return the report request and the presentation state it came from."""
        view = parse_view_state(self.mode, self.tab, self.comparison)
        return ReportRequest(
            pin=self.pin(),
            accounts=tuple(self.account),
            month=self.month,
            view=view,
            active_mode=(
                view.mode if self.active_mode is None else view_mode(self.active_mode)
            ),
        )


def _read_activity(
    dashboard: Dashboard,
    pin: tuple[int, date],
    accounts: Collection[str],
    month: str,
) -> AccountActivity | TemplateModule:
    """Return account activity for a pinned selection, or a failure fragment."""
    publication_id, reference_date = pin
    try:
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(accounts),
            month=parse_month(month),
            reference_date=reference_date,
        )
        with GoldStore(dashboard.profile, read_only=True) as store:
            return HouseholdReports(store).account_activity(context)
    except (InvalidSelectionError, PublicationUnavailableError) as error:
        return failure_fragment(dashboard, error)


def render_report(
    dashboard: Dashboard,
    requested: ReportRequest,
) -> TemplateModule:
    """Render the report fragment a selection asks for, or why it cannot be shown."""
    if not requested.accounts:
        # An empty selection is a prompt, never a report of nothing.
        return dashboard.templates.get_template("report/no_accounts.html").make_module()
    overview_report = read_overview(
        dashboard,
        requested.pin,
        requested.accounts,
        requested.month,
    )
    if isinstance(overview_report, TemplateModule):
        return overview_report
    answered = overview_report.context
    activity = (
        _read_activity(
            dashboard,
            requested.pin,
            requested.accounts,
            requested.month,
        )
        if requested.view.mode == "advanced" and requested.view.tab == "details"
        else None
    )
    if isinstance(activity, TemplateModule):
        return activity
    checks = (
        read_checks(
            dashboard,
            requested.pin,
            requested.accounts,
            requested.month,
        )
        if requested.view.mode == "advanced" and requested.view.tab == "checks"
        else None
    )
    if isinstance(checks, TemplateModule):
        return checks
    tab_links = switch_links(
        requested.view.tab,
        (
            (
                destination,
                f"tab-{destination}",
                pinned_url(
                    answered_address(answered),
                    view=ViewState(
                        "advanced",
                        destination,
                        requested.view.comparison,
                    ),
                ),
                label,
            )
            for destination, label in _TABS
        ),
    )
    unclassified_in, unclassified_out = unclassified_amounts(
        overview_report.unclassified
    )
    page = dashboard.templates.get_template("report/report.html")
    return page.make_module(
        {
            "notices": report_notices(requested.view, overview_report),
            "tab_template": tab_template(requested.view),
            "overview_notices": overview_notices(overview_report),
            "publication_id": answered.publication_id,
            "reference_date": answered.reference_date.isoformat(),
            "accounts": " ".join(sorted(answered.account_ids)),
            "month": month_value(answered.month),
            "month_label": month_label(answered.month),
            "overview": overview_report,
            "unclassified": overview_report.unclassified,
            "unclassified_in": unclassified_in,
            "unclassified_out": unclassified_out,
            "incomplete": [
                account_month.display_name
                for account_month in incomplete_months(overview_report.coverage)
            ],
            "activity": activity,
            "activity_accounts": account_rows(activity),
            "checks": checks,
            "mode": requested.view.mode,
            "tab": requested.view.tab,
            "comparison": requested.view.comparison,
            "tab_links": tab_links,
            "explanation_url": answered_url(
                overview_report,
                "/explanation",
                requested.view,
            ),
            "detail_urls": {
                category.category_id: detail_url(
                    answered,
                    "category",
                    category.category_id,
                    view=requested.view,
                )
                for category in overview_report.categories
            },
        }
    )


def _report_response(
    dashboard: Dashboard,
    requested: ReportRequest,
) -> Response:
    """Return the report fragment for one selection, or the empty-selection prompt.

    The address becomes this selection's own page, so back and forward reopen
    each selection the reader made.
    """
    view = parse_view_state(
        requested.view.mode,
        requested.view.tab,
        requested.view.comparison,
    )
    if view.mode != requested.active_mode:
        view = ViewState(view.mode, "overview", view.comparison)
    page = pinned_url(
        PinnedAddress(*requested.pin, requested.accounts, requested.month),
        view=view,
    )
    state = view_state_controls(dashboard.templates, view)
    fragment = render_report(
        dashboard,
        ReportRequest(
            requested.pin,
            requested.accounts,
            requested.month,
            view,
            view.mode,
        ),
    )
    return HTMLResponse(str(fragment) + state, headers={"HX-Push-Url": page})


def _register(dashboard: Dashboard) -> None:
    """Serve the report fragment at `/report` to a logged-in reader."""

    @dashboard.app.get("/report")
    def report(
        request: Request,
        address: Annotated[ReportAddress, Query()],
    ) -> Response:
        return dashboard.for_reader(
            request,
            lambda: _report_response(dashboard, address.asked()),
        )


REPORT = Feature(folder=Path(__file__).parent, register=_register)
