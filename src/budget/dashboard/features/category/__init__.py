# Copyright 2026 Therkel
"""The category page (`/category`): the entries behind one overview figure."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Self

from fastapi import Query, Request, Response
from fastapi.responses import HTMLResponse
from jinja2.environment import TemplateModule
from pydantic import BaseModel, model_validator

from budget.analytics import (
    DetailScope,
    DetailSubject,
    HouseholdReports,
    InvalidSelectionError,
    PublicationUnavailableError,
    ReportContext,
    SpendingDetail,
)
from budget.dashboard.addresses import answered_address, detail_url, pinned_url
from budget.dashboard.display.links import switch_links
from budget.dashboard.display.months import parse_month, period_label
from budget.dashboard.display.notices import newer_figures
from budget.dashboard.display.text import incomplete_by_account
from budget.dashboard.features import Dashboard, Feature
from budget.dashboard.features.errors import failure_fragment
from budget.dashboard.features.view_state import ViewState, parse_view_state
from budget.gold.store import GoldStore

# The periods a detail page switches between: scope, link id and label.
_SCOPES = (
    ("month", "scope-month", "Måned"),
    ("year_to_date", "scope-year-to-date", "År til dato"),
)


@dataclass(frozen=True)
class DetailRequest:
    """What a detail address asks for, beside the pinned publication and date."""

    accounts: tuple[str, ...]
    month: str
    subject: DetailSubject
    scope: DetailScope
    view: ViewState


class DetailAddress(BaseModel):
    """The query string of a detail page: the pin, the selection and the subject."""

    publication: int
    reference_date: date
    month: str
    account: list[str] = []
    category: str | None = None
    group: str | None = None
    scope: DetailScope = "month"
    mode: str = "simple"
    tab: str = "overview"
    comparison: str = "amounts"

    @model_validator(mode="after")
    def _names_one_subject(self) -> Self:
        """Refuse an address naming no subject, or both a Category and a group."""
        if (self.category is None) == (self.group is None):
            message = "name exactly one of category and group"
            raise ValueError(message)
        return self

    def asked(self) -> DetailRequest:
        """Return what the address asks for beside its pin."""
        subject = (
            DetailSubject("category", self.category)
            if self.category is not None
            else DetailSubject("group", self.group or "")
        )
        return DetailRequest(
            tuple(self.account),
            self.month,
            subject,
            self.scope,
            parse_view_state(self.mode, self.tab, self.comparison),
        )


def _read_detail(
    dashboard: Dashboard,
    pin: tuple[int, date],
    request: DetailRequest,
) -> SpendingDetail | TemplateModule:
    """Return the detail `request` asks for, or a fragment saying why not."""
    publication_id, reference_date = pin
    try:
        context = ReportContext(
            publication_id=publication_id,
            account_ids=frozenset(request.accounts),
            month=parse_month(request.month),
            reference_date=reference_date,
        )
        with GoldStore(dashboard.profile, read_only=True) as store:
            return HouseholdReports(store).spending_detail(
                context, request.subject, request.scope
            )
    except (InvalidSelectionError, PublicationUnavailableError) as error:
        return failure_fragment(dashboard, error)


def _render_detail(
    dashboard: Dashboard,
    pin: tuple[int, date],
    request: DetailRequest,
) -> str:
    """Render the detail page of one subject under one pinned selection."""
    detail_report = _read_detail(dashboard, pin, request)
    if isinstance(detail_report, TemplateModule):
        page = dashboard.templates.get_template("category/category_failure.html")
        return page.render(failure=detail_report)
    answered = detail_report.context
    subject = detail_report.subject
    period = period_label(detail_report.first_month, detail_report.last_month)
    return dashboard.templates.get_template("category/category.html").render(
        detail=detail_report,
        notices=newer_figures(detail_report.publication.is_current),
        is_group=subject.kind == "group",
        title=f"{detail_report.name}, {period}",
        scope_links=switch_links(
            detail_report.scope,
            (
                (
                    scope,
                    link_id,
                    detail_url(
                        answered,
                        subject.kind,
                        subject.id,
                        scope,
                        view=request.view,
                    ),
                    label,
                )
                for scope, link_id, label in _SCOPES
            ),
        ),
        group_url=detail_url(
            answered,
            "group",
            detail_report.group_id,
            detail_report.scope,
            view=request.view,
        ),
        incomplete=incomplete_by_account(detail_report.coverage),
        overview_url=pinned_url(answered_address(answered), view=request.view),
    )


def _register(dashboard: Dashboard) -> None:
    """Serve the category and group detail page at `/category` to a reader."""

    @dashboard.app.get("/category")
    def category_detail(
        request: Request, address: Annotated[DetailAddress, Query()]
    ) -> Response:
        return dashboard.for_reader(
            request,
            lambda: HTMLResponse(
                _render_detail(
                    dashboard,
                    (address.publication, address.reference_date),
                    address.asked(),
                )
            ),
        )


CATEGORY = Feature(folder=Path(__file__).parent, register=_register)
