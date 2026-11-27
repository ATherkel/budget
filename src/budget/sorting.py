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
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

from budget import checking
from budget.analytics import NothingPublishedError
from budget.gold.models import GoldTransaction
from budget.gold.store import GoldStore
from budget.inputs.rules import fold
from budget.locking import writer_lock
from budget.profiles import RULES_FILE_NAME, Profile
from budget.rebuilding import rebuild_from_gold
from budget.suggesting import slug, toml_string

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
    transactions, currencies = _published(profile)
    grouped: defaultdict[str, list[GoldTransaction]] = defaultdict(list)
    for transaction in transactions:
        if transaction.transaction_type == "unknown":
            grouped[group_key(transaction.description)].append(transaction)
    groups = [_group(key, members, currencies) for key, members in grouped.items()]
    return tuple(
        sorted(groups, key=lambda group: (-len(group.transactions), group.key))
    )


# Each column of the month totals, and the transaction types it adds up.
_COLUMNS: Final = (
    ("in", frozenset({"income"})),
    ("out", frozenset({"expense", "refund"})),
    ("transfer", frozenset({"transfer"})),
    ("unknown", frozenset({"unknown"})),
)


def month_totals(profile: Profile) -> tuple[str, ...]:
    """Return one line per month and currency: in, out, transfer and unknown."""
    transactions, currencies = _published(profile)
    sums: defaultdict[tuple[str, str], defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0.00"))
    )
    unknowns: defaultdict[tuple[str, str], int] = defaultdict(int)
    for transaction in transactions:
        month = transaction.transaction_date.strftime("%Y-%m")
        row = (month, currencies[transaction.account_id])
        sums[row][transaction.transaction_type] += transaction.amount
        unknowns[row] += transaction.transaction_type == "unknown"
    lines = []
    for (month, currency), by_type in sorted(sums.items()):
        columns = ", ".join(
            f"{name} {sum(by_type[kind] for kind in kinds)} {currency}"
            for name, kinds in _COLUMNS
        )
        count = unknowns[month, currency]
        noun = "transaction" if count == 1 else "transactions"
        lines.append(f"{month}  {columns} ({count} {noun})")
    return tuple(lines)


def _published(
    profile: Profile,
) -> tuple[tuple[GoldTransaction, ...], Mapping[str, str]]:
    """Return the current publication's transactions and each account's currency."""
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
    return tuple(transactions), currencies


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
        answer = input(_ASK).strip()
        if answer == "q":
            return
        if answer == "s":
            skipped.add(group.key)
            continue
        then = (
            "then.transfer_claim = true"
            if answer == "t"
            else f"then.category = {toml_string(answer)}"
        )
        rules = profile.input_file(RULES_FILE_NAME)
        _write_checked(profile, {rules: _with_rule(rules, group, then)})


def _write_checked(profile: Profile, writes: Mapping[Path, str]) -> None:
    """Write the files, then publish them, or put them back if `check` refuses.

    A refusal is shown with every problem `check` names, and nothing is left
    written, so the same group is asked again.
    """
    before = {path: path.read_bytes() if path.exists() else None for path in writes}
    for path, text in writes.items():
        path.write_text(text, encoding="utf-8", newline="\n")
    found = checking.check(profile)
    problems = (*found.problems, *found.mismatches)
    if problems:
        for path, content in before.items():
            if content is None:
                path.unlink()
            else:
                path.write_bytes(content)
        for problem in problems:
            _say(problem)
        _say("Nothing was written.")
        _say("")
        return
    with writer_lock(profile) as lock:
        rebuild_from_gold(lock, now=datetime.now(UTC))
    _say("Month totals")
    for line in month_totals(profile):
        _say(f"{_INDENT}{line}")
    _say("")


# What may stand between two words of a group's text: whitespace, numbers and
# dates, which the normalised text leaves out.
_GAP: Final = r"(?:\s|\d+(?:[./:-]\d+)*)"


def group_pattern(key: str) -> str:
    """Return a regex matching exactly the descriptions normalised to `key`.

    Rules match a regex ignoring case, as `fold` ignores it.
    """
    words = f"{_GAP}+".join(map(re.escape, key.split()))
    return f"^{_GAP}*{words}{_GAP}*$"


def _with_rule(path: Path, group: UnknownGroup, then: str) -> str:
    """Return `rules.toml` with one more rule, matching the group's text."""
    text = path.read_text(encoding="utf-8") if path.exists() else "format = 1\n"
    block = "\n".join(
        [
            f"# sorted: {group.key}",
            "[[rule]]",
            f"id = {toml_string('r-sort-' + slug(group.key))}",
            f"when.description_regex = {toml_string(group_pattern(group.key))}",
            then,
        ]
    )
    separator = "" if text.endswith("\n") else "\n"
    return f"{text}{separator}\n{block}\n"
