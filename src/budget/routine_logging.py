# Copyright 2026 Therkel
"""Routine JSON Lines logs: one record per finished command.

Every finished command appends one JSON object under the profile's `logs`
folder, and only what `operations.md` (*Logging*) allows: the command, the
profile, the event, counts, a duration, error codes, review-item kinds, and the
identifiers an import run, publication or decision is named by. Never an
amount, balance, description, bank category, original filename, bank account
number, account id, payload id, review id or transaction id.

The write is best effort. A log that cannot be written never changes the
command's outcome: a fixed warning is reported and the command still finishes,
so a build that has already replaced its store is not reported as failed.
"""

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from budget.profiles import Profile

LOG_FOLDER: Final = "logs"
LOG_FILE: Final = "commands.jsonl"
# A log file at or over this many bytes is renamed to the rotated name first,
# so the routine log stays bounded and keeps its newest records.
LOG_MAX_BYTES: Final = 1_000_000
ROTATED_LOG_FILE: Final = "commands.1.jsonl"
# The one thing a log failure says: never an operating system message.
LOG_WARNING: Final = "budget: the routine log could not be written\n"


def finished(
    profile: Profile,
    command: str,
    *,
    counts: Mapping[str, int],
    duration_ms: int,
    kinds: Sequence[str] = (),
) -> None:
    """Append one finished command's record, or warn and return.

    The caller names flat counts and review-item kinds, never a result object,
    a payload or an error message, so nothing unlisted can reach the record.
    """
    entry: dict[str, object] = {
        "command": command,
        "profile": profile.name,
        "event": "finished",
        "counts": dict(counts),
        "duration_ms": duration_ms,
        "review_item_kinds": sorted(set(kinds)),
    }
    try:
        _append(profile.stores / LOG_FOLDER, entry)
    except OSError:
        # The command has already succeeded; its outcome does not change.
        sys.stderr.write(LOG_WARNING)


def _append(folder: Path, entry: Mapping[str, object]) -> None:
    """Append one record, rotating a full log file aside first."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / LOG_FILE
    if path.exists() and path.stat().st_size >= LOG_MAX_BYTES:
        path.replace(folder / ROTATED_LOG_FILE)
    line = json.dumps(dict(entry), ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8", newline="\n") as log:
        log.write(line + "\n")
