# Copyright 2026 Therkel
"""Dashboard addresses: the pinned report and selection every page carries."""

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from budget.dashboard.features.view_state import DEFAULT_VIEW, DashboardMode, ViewState


@dataclass(frozen=True)
class PinnedAddress:
    """The report pin and selection carried by a dashboard address."""

    publication_id: int
    reference_date: date
    accounts: tuple[str, ...]
    month: str


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
