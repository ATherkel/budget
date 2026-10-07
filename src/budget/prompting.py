# Copyright 2026 Therkel
"""The conversation `budget import` holds at the terminal, before it stores.

Each inbox file is shown with its export date and its first and last
transaction dates, and the person types the range they asked the bank for
(operations.md, W1). Nothing is stored until they confirm. This is the
terminal, not the summary or a log, so a file is named here, by its filename,
so the person knows which export they are declaring.
"""

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Final

from budget.importing import Coverage
from budget.inbox import NO_ACCOUNT, ExportPreview

_INDENT: Final = "    "
_YES: Final = frozenset({"y", "yes"})


def _say(line: str) -> None:
    """Write one line of the conversation."""
    sys.stdout.write(f"{line}\n")


def _transactions(previewed: ExportPreview) -> str:
    """Describe the file's own transaction dates and how many records it has."""
    if previewed.failure_reason is not None:
        return f"none read: {previewed.failure_reason}"
    first, last = previewed.first_transaction, previewed.last_transaction
    if first is None or last is None:
        return "none"
    noun = "source record" if previewed.records == 1 else "source records"
    return f"{first}..{last}, {previewed.records} {noun}"


def _show(ordinal: int, previewed: ExportPreview) -> None:
    """Show one file: its account, name, export date and transaction dates."""
    name = previewed.source.name
    if previewed.account_id == NO_ACCOUNT:
        name = f"{previewed.source.parent.name}/{name}"
    _say(f"[{ordinal}] {previewed.account_id}  {name}")
    if previewed.skipped:
        _say(f"{_INDENT}{previewed.skipped}: {previewed.reason}; it stays in the inbox")
        return
    _say(f"{_INDENT}exported on    {previewed.exported_on} (from filename)")
    _say(f"{_INDENT}transactions   {_transactions(previewed)}")


def _ask_date(label: str) -> date:
    """Ask for one date until the answer is one. Raises `EOFError` at the end."""
    while True:
        answer = input(f"{_INDENT}{label}: ").strip()
        try:
            return date.fromisoformat(answer)
        except ValueError:
            _say(f"{_INDENT}not a date: type it as 2026-09-30")


def _confirmed(count: int) -> bool:
    """Ask once whether to import, defaulting to no."""
    noun = "file" if count == 1 else "files"
    return input(f"Import {count} {noun}? [y/N] ").strip().lower() in _YES


def ask_ranges(previews: Sequence[ExportPreview]) -> dict[Path, Coverage] | None:
    """Ask the range of every file that can be imported, then confirm.

    Returns each such file's declared range, or `None` when the person does
    not confirm or the input ends first: then nothing is to be stored.
    """
    declared: dict[Path, Coverage] = {}
    try:
        for ordinal, previewed in enumerate(previews, start=1):
            _show(ordinal, previewed)
            if previewed.skipped:
                continue
            _say(f"{_INDENT}Enter the range you asked the bank for.")
            declared[previewed.source] = Coverage(
                covers_from=_ask_date("from"), covers_through=_ask_date("through")
            )
        confirmed = not declared or _confirmed(len(declared))
    except EOFError:
        return None
    return declared if confirmed else None
