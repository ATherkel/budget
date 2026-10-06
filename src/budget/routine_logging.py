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
so a build that has already replaced its store is not reported as failed. Every
path it touches, the logs folder and both log files, is resolved through the
profile, so a test profile cannot let a log escape its temporary root.
"""

import json
import sys
from collections.abc import Mapping, Sequence
from typing import Final

from budget.profiles import LOGS_FOLDER, Profile, ProfilePathOutsideRootError

LOG_FOLDER: Final = LOGS_FOLDER
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
        _append(profile, entry)
    except (OSError, ProfilePathOutsideRootError):
        # A log outside its profile, or one that cannot be written, never
        # changes the command's outcome.
        sys.stderr.write(LOG_WARNING)


def _append(profile: Profile, entry: Mapping[str, object]) -> None:
    """Append one record, rotating a full log file aside first.

    Every path is resolved before anything is created, rotated or written, so a
    refused path leaves the profile exactly as it was.
    """
    folder = profile.logs_folder
    path = profile.log_file(LOG_FILE)
    rotated = profile.log_file(ROTATED_LOG_FILE)
    folder.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= LOG_MAX_BYTES:
        path.replace(rotated)
    line = json.dumps(dict(entry), ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8", newline="\n") as log:
        log.write(line + "\n")
