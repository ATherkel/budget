# Copyright 2026 Therkel
"""Dashboard addresses: the pinned report and selection every page carries."""

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from pydantic import BaseModel

from budget.analytics import MonthlyOverview, ReportContext
from budget.dashboard.display.months import month_value
from budget.dashboard.features.view_state import DEFAULT_VIEW, DashboardMode, ViewState


@dataclass(frozen=True)
class PinnedAddress:
    """The report pin and selection carried by a dashboard address."""

    publication_id: int
    reference_date: date
    accounts: tuple[str, ...]
    month: str


class PinnedQuery(BaseModel):
    """Required query parameters shared by pinned report pages."""

    publication: int
    reference_date: date
    month: str
    account: list[str] = []
    mode: str = "simple"
    tab: str = "overview"
    comparison: str = "amounts"

    def pin(self) -> tuple[int, date]:
        """Return this address's publication and reference date."""
        return (self.publication, self.reference_date)


@dataclass(frozen=True)
class ReportRequest:
    """A report request under one pinned presentation state."""

    pin: tuple[int, date]
    accounts: tuple[str, ...]
    month: str
    view: ViewState
    active_mode: DashboardMode


def pinned_url(
    address: PinnedAddress,
    path: str = "/",
    *,
    view: ViewState = DEFAULT_VIEW,
) -> str:
    """Return the complete address of `path` for one pinned selection."""
    return f"{path}?" + urlencode(
        [
            ("publication", address.publication_id),
            ("reference_date", address.reference_date.isoformat()),
            *(("account", account) for account in sorted(address.accounts)),
            ("month", address.month),
            ("mode", view.mode),
            ("tab", view.tab),
            ("comparison", view.comparison),
        ]
    )


def _answered_address(answered: ReportContext) -> PinnedAddress:
    """Return the pinned address of the context a report answered."""
    return PinnedAddress(
        answered.publication_id,
        answered.reference_date,
        tuple(answered.account_ids),
        month_value(answered.month),
    )


def answered_url(
    overview_report: MonthlyOverview,
    path: str,
    view: ViewState = DEFAULT_VIEW,
) -> str:
    """Return the address of `path` for the context `overview_report` answers."""
    return pinned_url(_answered_address(overview_report.context), path, view=view)


def detail_url(
    answered: ReportContext,
    kind: str,
    subject_id: str,
    scope: str = "month",
    *,
    view: ViewState = DEFAULT_VIEW,
) -> str:
    """Return the address of one subject's detail under the pinned `answered`."""
    page = pinned_url(_answered_address(answered), "/category", view=view)
    return f"{page}&" + urlencode([(kind, subject_id), ("scope", scope)])
