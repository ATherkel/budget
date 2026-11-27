# Copyright 2026 Therkel
"""What the report prints, prepared so its templates only loop and print."""

from typing import NamedTuple

from budget.analytics import (
    AccountActivity,
    AccountActivitySnapshot,
    MonthlyOverview,
)
from budget.dashboard.display.notices import Notice, newer_figures, shown
from budget.dashboard.features.report.account_cards import (
    account_cards,
    activity_table,
)
from budget.dashboard.features.report.card import Card, Table
from budget.dashboard.features.view_state import ViewState

_NO_ROWS = "Ingen observerede posteringer i måneden."
# Each tab of the advanced mode and the template that shows it.
_TAB_TEMPLATES = {
    "overview": "report/overview_tab.html",
    "details": "report/activity.html",
    "checks": "checks/checks.html",
}


class AccountRows(NamedTuple):
    """One account in Detaljer: its observations and its own transactions."""

    account: AccountActivitySnapshot
    table: Table
    cards: tuple[Card, ...]


def report_notices(view: ViewState, overview: MonthlyOverview) -> tuple[Notice, ...]:
    """Return the notes above the report's tab, in the order the report shows them."""
    return (
        *shown((view.mode == "advanced", Notice("report/advanced_tabs.html"))),
        *newer_figures(overview.publication),
        *shown(
            (overview.provisional is not None, Notice("report/provisional_note.html")),
            (
                overview.coverage.status != "complete",
                Notice("report/coverage_note.html"),
            ),
        ),
    )


def tab_template(view: ViewState) -> str:
    """Return the template of the tab `view` shows; the simple mode's is Overblik."""
    return _TAB_TEMPLATES[view.tab]


def overview_notices(overview: MonthlyOverview) -> tuple[Notice, ...]:
    """Return the parts of Overblik below its summary that apply, in order."""
    unclassified = overview.unclassified
    return shown(
        (
            unclassified is not None and unclassified.count > 0,
            Notice("report/unclassified_note.html"),
        ),
        (bool(overview.categories), Notice("report/categories.html")),
    )


def account_rows(activity: AccountActivity | None) -> tuple[AccountRows, ...]:
    """Return each account of `activity` with its own rows, in their order.

    Without activity, as on a tab other than Detaljer, there are no accounts.
    """
    if activity is None:
        return ()
    grouped = []
    for account in activity.accounts:
        rows = tuple(
            row for row in activity.transactions if row.account_id == account.account_id
        )
        grouped.append(
            AccountRows(
                account,
                activity_table(
                    f"Posteringer for {account.display_name}",
                    rows,
                    activity.currency,
                    _NO_ROWS,
                ),
                account_cards(account, rows, activity.currency),
            )
        )
    return tuple(grouped)
