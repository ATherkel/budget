# Copyright 2026 Therkel
"""The `sort` application operation: unknown transactions, one group at a time.

The current publication's unknowns are grouped by their normalised
description, so one answer can classify every transaction a group holds.
"""

import re
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from budget.analytics import NothingPublishedError
from budget.gold.models import GoldTransaction
from budget.gold.store import GoldStore
from budget.inputs.rules import fold
from budget.profiles import Profile

# A run of digits, with the separators a date or a number carries between them.
_NUMBERS: Final = re.compile(r"\d+(?:[./:-]\d+)*")
_EXAMPLES: Final = 3
_INDENT: Final = "  "
_ASK: Final = "Category, t (transfer), n (new category), s (skip) or q (quit): "


def group_key(description: str) -> str:
    """Normalise a description: case folded, numbers and dates gone, spaces single."""
    return " ".join(_NUMBERS.sub(" ", fold(description)).split())


@dataclass(frozen=True)
class UnknownGroup:
    """The unknown transactions that share one normalised description."""

    key: str
    # In date order.
    transactions: tuple[GoldTransaction, ...]
    # The signed sum in each currency, never added across currencies.
    sums: Mapping[str, Decimal]


def unknown_groups(profile: Profile) -> tuple[UnknownGroup, ...]:
    """Return the current publication's unknowns by group, the biggest first."""
    if not profile.gold_store.exists():
        raise NothingPublishedError
    with GoldStore(profile, read_only=True) as store:
        publication = store.current()
        if publication is None:
            raise NothingPublishedError
        gold = store.open(publication.publication_id)
        transactions = gold.transactions(
            start_date=date.min, end_date=date.max, account_ids=None
        )
        currencies = {
            account.account_id: account.currency for account in gold.accounts()
        }
    grouped: defaultdict[str, list[GoldTransaction]] = defaultdict(list)
    for transaction in transactions:
        if transaction.transaction_type == "unknown":
            grouped[group_key(transaction.description)].append(transaction)
    groups = [_group(key, members, currencies) for key, members in grouped.items()]
    return tuple(
        sorted(groups, key=lambda group: (-len(group.transactions), group.key))
    )


def _group(
    key: str, members: list[GoldTransaction], currencies: Mapping[str, str]
) -> UnknownGroup:
    """Build one group: its members in date order and its sum per currency."""
    sums: defaultdict[str, Decimal] = defaultdict(Decimal)
    for member in members:
        sums[currencies[member.account_id]] += member.amount
    ordered = sorted(
        members,
        key=lambda t: (t.transaction_date, t.account_id, t.account_sequence),
    )
    return UnknownGroup(key=key, transactions=tuple(ordered), sums=dict(sums))


def _say(line: str) -> None:
    """Write one line of the conversation."""
    sys.stdout.write(f"{line}\n")


def _show(group: UnknownGroup) -> None:
    """Show a group: its text, its size and sum, and its first examples."""
    count = len(group.transactions)
    noun = "transaction" if count == 1 else "transactions"
    sums = ", ".join(
        f"{total} {currency}" for currency, total in sorted(group.sums.items())
    )
    _say(group.key)
    _say(f"{_INDENT}{count} {noun}, {sums}")
    for example in group.transactions[:_EXAMPLES]:
        _say(
            f"{_INDENT}{example.transaction_date}  {example.account_id}  "
            f"{example.amount}  {example.description}"
        )
    _say("")


def sort_unknowns(profile: Profile) -> None:
    """Hold the sorting conversation over the current publication's unknowns."""
    skipped: set[str] = set()
    while True:
        group = next(
            (each for each in unknown_groups(profile) if each.key not in skipped), None
        )
        if group is None:
            _say("No group is left to sort.")
            return
        _show(group)
        if input(_ASK).strip() == "q":
            return
        skipped.add(group.key)
