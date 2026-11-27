# Copyright 2026 Therkel
"""The `sort` application operation: unknown transactions, one group at a time.

The current publication's unknowns are grouped by their normalised
description, so one answer can classify every transaction a group holds.
"""

import os
import re
import subprocess
import sys
import tempfile
import tomllib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from budget import checking
from budget.analytics import NothingPublishedError
from budget.backups import back_up
from budget.codeversion import require_committed_code
from budget.gold.models import GoldTransaction
from budget.gold.store import GoldStore
from budget.inputs.rules import fold
from budget.locking import writer_lock
from budget.profiles import (
    PRODUCTION_PROFILE_NAME,
    RULES_FILE_NAME,
    TAXONOMY_FILE_NAME,
    Profile,
)
from budget.rebuilding import rebuild_from_gold
from budget.suggesting import slug, toml_string, unique_id

# A run of digits, with the separators a date or a number carries between them.
_NUMBERS: Final = re.compile(r"\d+(?:[./:-]\d+)*")
_EXAMPLES: Final = 3
_INDENT: Final = "  "
_ASK: Final = (
    "[t] transfer  [n] new category  [s] skip  [m] months  [?] category list  "
    "[q] quit  or type a word to search: "
)


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


# Each money column of the month table, and the kinds it adds up. Unknown is
# split by sign, so money in and out never net to a settled-looking month.
_COLUMNS: Final = (
    ("In", frozenset({"income"})),
    ("Out", frozenset({"expense", "refund"})),
    ("Transfer", frozenset({"transfer"})),
    ("Unknown in", frozenset({"unknown in"})),
    ("Unknown out", frozenset({"unknown out"})),
)


def _kind(transaction: GoldTransaction) -> str:
    """Name the column kind of a transaction: its type, or unknown in or out."""
    if transaction.transaction_type != "unknown":
        return transaction.transaction_type
    return "unknown in" if transaction.amount > 0 else "unknown out"


def month_table(profile: Profile) -> tuple[str, ...]:
    """Return the month table: a header, then one row per month and currency.

    Month and currency are aligned left, every amount right.
    """
    transactions, currencies = _published(profile)
    sums: defaultdict[tuple[str, str], defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0.00"))
    )
    for transaction in transactions:
        month = transaction.transaction_date.strftime("%Y-%m")
        row = (month, currencies[transaction.account_id])
        sums[row][_kind(transaction)] += transaction.amount
    rows = [
        [month, currency]
        + [str(sum(by_kind[kind] for kind in kinds)) for _, kinds in _COLUMNS]
        for (month, currency), by_kind in sorted(sums.items())
    ]
    header = ["Month", "Currency", *(name for name, _ in _COLUMNS)]
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]

    def line(cells: Sequence[str]) -> str:
        left = [
            cell.ljust(width) for cell, width in zip(cells[:2], widths[:2], strict=True)
        ]
        right = [
            cell.rjust(width) for cell, width in zip(cells[2:], widths[2:], strict=True)
        ]
        return "  ".join([*left, *right])

    return tuple(line(cells) for cells in [header, *rows])


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


def open_in_default_app(path: Path) -> None:
    """Open a file in the operating system's default app for it.

    The one place `sort` reaches outside the terminal, so tests replace it.
    """
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - the household's own file, its own app
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, str(path)], check=False)  # noqa: S603


def _say(line: str) -> None:
    """Write one line of the conversation."""
    sys.stdout.write(f"{line}\n")


def _show(group: UnknownGroup) -> None:
    """Show a group: its text, size and sum, what an answer covers, and examples.

    The answer becomes a rule, so it also covers later transactions that
    normalise to the same text.
    """
    count = len(group.transactions)
    noun = "transaction" if count == 1 else "transactions"
    sums = " and ".join(
        f"{total:,} {currency}" for currency, total in sorted(group.sums.items())
    )
    covers = "this one" if count == 1 else f"all {count}"
    _say(f'"{group.key}": {count} {noun}, {sums} in total')
    _say(f"Your answer applies to {covers}, and to future ones with this text.")
    _say("For example:")
    for example in group.transactions[:_EXAMPLES]:
        _say(
            f"{_INDENT}{example.transaction_date}  {example.account_id}  "
            f"{example.amount}  {example.description}"
        )
    _say("")


type _Listed = tuple[tuple[str, tuple[tuple[str, str], ...]], ...]

CATEGORY_LIST_NAME: Final = "budget-categories.md"


def _open_category_list(categories: _Listed) -> None:
    """Write the categories to a temporary file and open it, or say there are none.

    Each group's name heads its categories, each with its name and ID, so the
    list is read beside the terminal instead of filling it.
    """
    if not categories:
        _say("No categories yet: type n to add one")
        return
    lines = ["# Categories"]
    for group_name, members in categories:
        lines += ["", f"## {group_name}", ""]
        lines += [f"- {name} ({category_id})" for category_id, name in members]
    path = Path(tempfile.gettempdir()) / CATEGORY_LIST_NAME
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    open_in_default_app(path)
    _say("Opened the category list in your editor. Type a word to search, or an id.")


def _taxonomy(profile: Profile) -> dict[str, Any]:
    """Read `taxonomy.toml` as TOML, or nothing when it is missing or unreadable.

    `check` judges the file; this only needs what it can read of it.
    """
    path = profile.input_file(TAXONOMY_FILE_NAME)
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _name(table: object, default: str) -> str:
    """Return a taxonomy table's `name`, or `default` when it has none."""
    return str(table.get("name", default)) if isinstance(table, dict) else default


def _categories(document: Mapping[str, Any]) -> _Listed:
    """Return each group's name and its categories' IDs and names, in file order."""
    groups = document.get("group", {})
    categories = document.get("category", {})
    listed = []
    for group_id, group in groups.items():
        members = tuple(
            (str(category_id), _name(category, str(category_id)))
            for category_id, category in categories.items()
            if isinstance(category, dict) and category.get("group") == group_id
        )
        if members:
            listed.append((_name(group, str(group_id)), members))
    return tuple(listed)


def sort_unknowns(profile: Profile) -> None:
    """Hold the sorting conversation over the current publication's unknowns.

    The input ending quits, as `q` does: every answer is published as it is
    given, so nothing is left to undo. Production refuses uncommitted code
    before anything is asked, as `budget rebuild` does.
    """
    require_committed_code(profile)
    try:
        _converse(profile)
    except EOFError:
        _say("")


def _converse(profile: Profile) -> None:
    """Ask about each group, the biggest first, until none is left or `q`."""
    skipped: set[str] = set()
    # The category IDs of the last search, which a number picks from.
    picks: list[str] = []
    while True:
        group = next(
            (each for each in unknown_groups(profile) if each.key not in skipped), None
        )
        if group is None:
            _say("No group is left to sort.")
            return
        categories = _categories(_taxonomy(profile))
        _show(group)
        answer = _resolve(input(_ASK).strip(), categories, picks)
        if answer is None:
            _say("")
            continue
        if answer == "q":
            return
        if answer == "s":
            skipped.add(group.key)
        else:
            _answer(profile, group, answer, categories)


def _answer(
    profile: Profile, group: UnknownGroup, answer: str, categories: _Listed
) -> None:
    """Show the list or the month table asked for, or classify the group."""
    if answer == "?":
        _open_category_list(categories)
    elif answer == "m":
        for line in month_table(profile):
            _say(line)
    else:
        _classify(profile, group, answer)
        return
    _say("")


def _classify(profile: Profile, group: UnknownGroup, answer: str) -> None:
    """Turn a category, `t` or `n` into the files' new text, then write it."""
    writes: dict[Path, str] = {}
    if answer == "n":
        taxonomy = profile.input_file(TAXONOMY_FILE_NAME)
        category_id, writes[taxonomy] = _with_category(taxonomy, group)
        then = f"then.category = {toml_string(category_id)}"
    elif answer == "t":
        then = "then.transfer_claim = true"
    else:
        then = f"then.category = {toml_string(answer)}"
    rules = profile.input_file(RULES_FILE_NAME)
    writes[rules] = _with_rule(rules, group, then)
    _write_checked(profile, writes)


_COMMANDS: Final = frozenset({"q", "s", "m", "?", "t", "n"})
# A search shows no more matches than one can read at a glance.
_MATCHES: Final = 8


def _resolve(answer: str, categories: _Listed, picks: list[str]) -> str | None:
    """Return the command or category ID an answer names, or `None` after a search.

    A number picks from the last search; any other text that is no command
    and no category ID searches, and its matches become what a number picks.
    """
    ids = {category_id for _, members in categories for category_id, _ in members}
    if answer in _COMMANDS or answer in ids:
        return answer
    if answer.isdecimal() and 1 <= int(answer) <= len(picks):
        return picks[int(answer) - 1]
    matches = [
        (category_id, name)
        for _, members in categories
        for category_id, name in members
        if fold(answer) in fold(category_id) or fold(answer) in fold(name)
    ]
    more = len(matches) - _MATCHES
    matches = matches[:_MATCHES]
    picks[:] = [category_id for category_id, _ in matches]
    if not matches:
        _say(f'No category matches "{answer}".')
        return None
    _say(f'Matches for "{answer}":')
    for number, (category_id, name) in enumerate(matches, start=1):
        _say(f"{_INDENT}{number} {name} ({category_id})")
    if more > 0:
        _say(f"{_INDENT}and {more} more: type more of the word")
    return None


def _with_category(path: Path, group: UnknownGroup) -> tuple[str, str]:
    """Ask a new category's name and group; return its ID and the new taxonomy.

    A group the taxonomy does not hold yet is added, and its direction asked,
    offering the one the group's sum suggests.
    """
    text = path.read_text(encoding="utf-8") if path.exists() else "format = 1\n"
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        document = {}
    name = input(f"{_INDENT}name: ").strip()
    group_answer = input(f"{_INDENT}group: ").strip()
    tables: list[str] = []
    groups = document.get("group", {})
    group_id = group_answer
    if group_answer not in groups:
        group_id = unique_id(slug(group_answer), set(groups))
        offered = "income" if all(s > 0 for s in group.sums.values()) else "expense"
        direction = input(f"{_INDENT}direction [{offered}]: ").strip() or offered
        tables.append(
            f"[group.{group_id}]\nname = {toml_string(group_answer)}\n"
            f"direction = {toml_string(direction)}\n"
        )
    category_id = unique_id(slug(name), set(document.get("category", {})))
    tables.append(
        f"[category.{category_id}]\nname = {toml_string(name)}\n"
        f"group = {toml_string(group_id)}\n"
    )
    separator = "" if text.endswith("\n") else "\n"
    return category_id, text + separator + "".join(f"\n{table}" for table in tables)


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
        _put_back(before)
        for problem in problems:
            _say(problem)
        _say("Nothing was written.")
        _say("")
        return
    _publish(profile)


def _put_back(before: Mapping[Path, bytes | None]) -> None:
    """Return each file to what it held, removing one that did not exist."""
    for path, content in before.items():
        if content is None:
            path.unlink()
        else:
            path.write_bytes(content)


def _publish(profile: Profile) -> None:
    """Publish Gold from the written files, then show the month totals."""
    with writer_lock(profile) as lock:
        rebuilt = rebuild_from_gold(lock, now=datetime.now(UTC))
        # Every production write is followed by a set covering it, as for
        # `budget rebuild`.
        if profile.name == PRODUCTION_PROFILE_NAME and rebuilt.published:
            written = back_up(lock, now=datetime.now(UTC))
            _say(f"Backup   backup set {written.name} written")
    _say(progress(profile))
    _say("")


def progress(profile: Profile) -> str:
    """Say how much of the publication is sorted, and the unknown money left.

    Unknown money in and out are summed apart in each currency, never netted,
    so a month of both does not look settled.
    """
    transactions, currencies = _published(profile)
    unknown = [t for t in transactions if t.transaction_type == "unknown"]
    money_in: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    money_out: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for transaction in unknown:
        side = money_in if transaction.amount > 0 else money_out
        side[currencies[transaction.account_id]] += transaction.amount
    sides = ", ".join(
        f"in {money_in[currency]} {currency}, out {money_out[currency]} {currency}"
        for currency in sorted({*money_in, *money_out})
    )
    total = len(transactions)
    sorted_count = total - len(unknown)
    percent = round(100 * sorted_count / total) if total else 100
    left = f"{len(unknown)} unknown left" + (f": {sides}" if sides else "")
    return f"Sorted {sorted_count} of {total} ({percent}%), {left}"


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
