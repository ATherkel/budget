# Copyright 2026 Therkel
"""What the selection form offers: its months, modes, accounts and shortcuts."""

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from budget.dashboard.display.months import month_label, month_value, months_between
from budget.gold import ReportingMonth

type Attributes = dict[str, str | None]

# The report's modes, in the order the form offers them: value and label.
_MODES = (("simple", "Enkel"), ("advanced", "Avanceret"))


@dataclass(frozen=True)
class Choice:
    """One choice the form offers: its label and its control's attributes."""

    label: str
    # Rendered with `xmlattr`, which leaves out an attribute whose value is None.
    attributes: Attributes


def _marked(attribute: str, *, chosen: bool) -> str | None:
    """Return a boolean attribute's value: present when `chosen`, else left out."""
    return attribute if chosen else None


def month_options(
    first: ReportingMonth, last: ReportingMonth, selected: str
) -> list[Choice]:
    """Return each month from `first` to `last`, the `selected` one selected."""
    return [
        Choice(
            month_label(month),
            {
                "value": month_value(month),
                "selected": _marked("selected", chosen=month_value(month) == selected),
            },
        )
        for month in months_between(first, last)
    ]


def mode_options(current: str) -> list[Choice]:
    """Return a radio button per mode, the `current` one checked."""
    return [
        Choice(
            label,
            {
                "type": "radio",
                "name": "mode",
                "value": value,
                "aria-label": label,
                "checked": _marked("checked", chosen=value == current),
            },
        )
        for value, label in _MODES
    ]


def account_inputs(
    account_ids: Sequence[str], selected: Collection[str]
) -> dict[str, Attributes]:
    """Return each account's checkbox attributes, keyed by its id."""
    return {
        account_id: {
            "type": "checkbox",
            "name": "account",
            "value": account_id,
            "checked": _marked("checked", chosen=account_id in selected),
        }
        for account_id in account_ids
    }


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
