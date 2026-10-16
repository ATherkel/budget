# Copyright 2026 Therkel
"""The conversation `budget import` holds at the terminal, before it stores.

Each inbox file is shown with its export date and its first and last
transaction dates, and the person types the range they asked the bank for
(operations.md, W1). Nothing is stored until they confirm. This is the
terminal, not the summary or a log, so a file is named here, by its filename,
so the person knows which export they are declaring.

A payload the inbox holds under more than one account is a cross-account
duplicate: every file it holds is shown before any range is asked, because
which of them the bank really exported is unknown until a person checks. Every
file in it stays in the inbox, and the rest is imported only if they go on.
"""

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Final

from budget.importing import Coverage
from budget.inbox import INCIDENT_REASON, NO_ACCOUNT, DuplicateIncident, ExportPreview

_INDENT: Final = "    "
_YES: Final = frozenset({"y", "yes"})
_CONTINUE_ANYWAY: Final = "Continue anyway? [y/N] "


def _say(line: str) -> None:
    """Write one line of the conversation."""
    sys.stdout.write(f"{line}\n")


def _transactions(previewed: ExportPreview) -> str:
    """Describe the file's own transaction dates and how many records it has."""
    first, last = previewed.first_transaction, previewed.last_transaction
    if first is None or last is None:
        return "none"
    noun = "source record" if previewed.records == 1 else "source records"
    return f"{first}..{last}, {previewed.records} {noun}"


def _details(previewed: ExportPreview) -> None:
    """Describe one file under its name: why it is skipped, or what it holds."""
    if previewed.skipped:
        _say(f"{_INDENT}{previewed.skipped}: {previewed.reason}; it stays in the inbox")
        return
    _say(f"{_INDENT}exported on    {previewed.exported_on} (from filename)")
    _say(f"{_INDENT}transactions   {_transactions(previewed)}")


def _show(ordinal: int, previewed: ExportPreview, excluded: frozenset[Path]) -> None:
    """Show one file: its account, name, dates, and why it is not imported.

    A file an incident holds is named as staying in the inbox, so the person
    sees why it is asked no range.
    """
    name = previewed.source.name
    if previewed.account_id == NO_ACCOUNT:
        name = f"{previewed.source.parent.name}/{name}"
    _say(f"[{ordinal}] {previewed.account_id}  {name}")
    _details(previewed)
    if previewed.source in excluded:
        _say(f"{_INDENT}incident: {INCIDENT_REASON}; it stays in the inbox")


def _ask_date(label: str, previous: date | None) -> date:
    """Ask for one date until the answer is one. Raises `EOFError` at the end.

    With `previous`, the answer given for the file before, the prompt shows
    it, and an empty answer gives it again: an inbox of one download batch
    shares one range, and retyping it for every file invites a slip.
    """
    offered = "" if previous is None else f" [{previous}]"
    while True:
        answer = input(f"{_INDENT}{label}{offered}: ").strip()
        if not answer and previous is not None:
            return previous
        try:
            return date.fromisoformat(answer)
        except ValueError:
            _say(f"{_INDENT}not a date: type it as 2026-09-30")


def _confirmed(count: int) -> bool:
    """Ask once whether to import, defaulting to no."""
    noun = "file" if count == 1 else "files"
    return input(f"Import {count} {noun}? [y/N] ").strip().lower() in _YES


def a_terminal_is_available() -> bool:
    """Report whether the person can be asked: standard input is a terminal."""
    isatty = getattr(sys.stdin, "isatty", None)
    return bool(isatty is not None and isatty())


def _show_duplicates(incidents: Sequence[DuplicateIncident]) -> None:
    """Show every file the incidents hold, with what the person must check."""
    counted = sum(len(incident.files) for incident in incidents)
    noun = "incident" if len(incidents) == 1 else "incidents"
    files = "file" if counted == 1 else "files"
    _say(
        f"Cross-account duplicates: {len(incidents)} {noun}, {counted} {files} impacted"
    )
    for ordinal, incident in enumerate(incidents, start=1):
        noun = "file" if len(incident.files) == 1 else "files"
        _say(f"Duplicate {ordinal} ({len(incident.files)} {noun})")
        for previewed in incident.files:
            _say(f"{previewed.account_id}  {previewed.source.name}")
            _details(previewed)
    _say(
        "Check which account the bank exported it from, then download the "
        "affected accounts again; every file above stays in the inbox and "
        "none of them is imported."
    )


def ask_continue_after_duplicates(incidents: Sequence[DuplicateIncident]) -> bool:
    """Show each cross-account duplicate, then ask whether to import the rest.

    Only `y` or `yes` typed at a terminal goes on. With nobody at a terminal
    to ask, and with every other answer, all the files stay where they are and
    nothing is imported.
    """
    _show_duplicates(incidents)
    if not a_terminal_is_available():
        return False
    try:
        return input(_CONTINUE_ANYWAY).strip().lower() in _YES
    except EOFError:
        return False


def ask_ranges(
    previews: Sequence[ExportPreview], excluded: frozenset[Path]
) -> dict[Path, Coverage] | None:
    """Ask the range of every file the import will use, then confirm.

    A file an incident holds is asked no range: it is not going to be
    imported. Returns each file that will be imported with its declared range,
    or `None` when the person does not confirm or the input ends first: then
    nothing is to be stored.
    """
    declared: dict[Path, Coverage] = {}
    previous: Coverage | None = None
    try:
        for ordinal, previewed in enumerate(previews, start=1):
            _show(ordinal, previewed, excluded)
            if previewed.skipped or previewed.source in excluded:
                continue
            _say(f"{_INDENT}Enter the range you asked the bank for.")
            previous = Coverage(
                covers_from=_ask_date(
                    "from", None if previous is None else previous.covers_from
                ),
                covers_through=_ask_date(
                    "through", None if previous is None else previous.covers_through
                ),
            )
            declared[previewed.source] = previous
        confirmed = not declared or _confirmed(len(declared))
    except EOFError:
        return None
    return declared if confirmed else None
