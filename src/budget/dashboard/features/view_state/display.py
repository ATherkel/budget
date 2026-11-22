# Copyright 2026 Therkel
"""What the selection form offers: its months and its account shortcuts."""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from budget.dashboard.display.months import month_label, month_value, months_between
from budget.gold import ReportingMonth


def month_choices(first: ReportingMonth, last: ReportingMonth) -> list[tuple[str, str]]:
    """Return each month from `first` to `last` as its address value and label."""
    return [
        (month_value(month), month_label(month))
        for month in months_between(first, last)
    ]


@dataclass(frozen=True)
class AccountShortcuts:
    """The addresses of the selection's "Alle", "Ingen" and "kun" links."""

    all_url: str
    none_url: str
    # Keyed by account id: that account selected on its own.
    only_urls: dict[str, str]


def account_shortcuts(
    account_ids: Sequence[str],
    selecting: Callable[[Collection[str]], str],
) -> AccountShortcuts:
    """Return the shortcut addresses, given the address `selecting` some accounts."""
    return AccountShortcuts(
        all_url=selecting(account_ids),
        none_url=selecting([]),
        only_urls={account_id: selecting([account_id]) for account_id in account_ids},
    )
