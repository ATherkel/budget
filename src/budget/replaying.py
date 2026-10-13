# Copyright 2026 Therkel
"""Replay the import log into Bronze, from the export archive.

`imports.jsonl` holds what exists nowhere outside Bronze: each run's ID,
declarations, timestamp and outcome. With the archived bytes it names, it
rebuilds Bronze's history exactly, into an empty store or onto a restored
store that holds a prefix of it.
"""

import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from hashlib import sha256
from typing import Final, Literal

from budget.bronze import BronzeStore, ImportRun
from budget.importing import IMPORT_LOG_FORMAT, archive_candidates
from budget.locking import WriterLock
from budget.profiles import Profile

# Every field an entry holds, no more and no fewer.
_ENTRY_FIELDS: Final = frozenset(
    {
        "format",
        "import_run_id",
        "account_id",
        "source_format",
        "archive_path",
        "payload_sha256",
        "exported_on",
        "exported_on_source",
        "covers_from",
        "covers_through",
        "started_at",
        "outcome",
        "repeat_of",
    }
)
_OUTCOMES: Final[Mapping[str, Literal["stored", "repeat", "refused"]]] = {
    "stored": "stored",
    "repeat": "repeat",
    "refused": "refused",
}
_DATE_SOURCES: Final[Mapping[str, Literal["filename", "declared"]]] = {
    "filename": "filename",
    "declared": "declared",
}
_SHA256: Final = re.compile("[0-9a-f]{64}")


class ArchivedExportMissingError(RuntimeError):
    """No file stands where a logged run's entry says its export is archived.

    The runs before it stay restored, and nothing of this run is written. The
    message names the run, never a filename.
    """

    def __init__(self, import_run_id: str) -> None:
        """Name the run whose archived export is missing."""
        self.import_run_id = import_run_id
        super().__init__(
            f"import run {import_run_id}: the export archive holds no file where "
            "its log entry says the export is archived; nothing of the run was "
            "restored. Put the export back there, then rerun."
        )


class ArchivedExportMismatchError(RuntimeError):
    """The file where a logged run is archived is not the bytes its entry names.

    The runs before it stay restored, and nothing of this run is written. The
    message names the run, never a filename.
    """

    def __init__(self, import_run_id: str) -> None:
        """Name the run whose archived bytes do not match its entry."""
        self.import_run_id = import_run_id
        super().__init__(
            f"import run {import_run_id}: the archived export's SHA-256 is not "
            "the one its log entry names; nothing of the run was restored. Put "
            "the run's own export back there, then rerun."
        )


class ImportLogInvalidError(RuntimeError):
    """A complete line of the import log is not a valid entry.

    The whole log is checked before anything is written, so nothing was
    restored. The message names the line by number, never its content.
    """

    def __init__(self, line_number: int) -> None:
        """Name the first line that is not a valid entry."""
        self.line_number = line_number
        super().__init__(
            f"imports.jsonl line {line_number} is not a valid import-log entry; "
            "nothing was restored. Restore the log from the newest backup set."
        )


class RunConflictError(RuntimeError):
    """Bronze holds a logged run's ID, but not as the log records the run.

    History is never overwritten, so nothing more is restored.
    """

    def __init__(self, import_run_id: str) -> None:
        """Name the run Bronze and the log disagree about."""
        self.import_run_id = import_run_id
        super().__init__(
            f"import run {import_run_id}: Bronze holds this run otherwise than "
            "the import log records it; nothing more was restored. Restore "
            "Bronze from a backup set that matches the log, or replay into an "
            "empty store."
        )


class NotALogPrefixError(RuntimeError):
    """Bronze holds runs that are not the import log's first runs, in order.

    A replay only continues history Bronze already shares with the log, so
    nothing is restored.
    """

    def __init__(self) -> None:
        """State the problem and its remedy, without quoting the log."""
        super().__init__(
            "Bronze holds import runs that are not the import log's first runs, "
            "in order; nothing was restored. Restore Bronze from a backup set "
            "taken from this log, or replay into an empty store."
        )


class UnknownRepeatOfError(RuntimeError):
    """A logged repeat names no run restored before it.

    The runs before it stay restored, and nothing of this run is written.
    """

    def __init__(self, import_run_id: str) -> None:
        """Name the run whose repeat link points nowhere."""
        self.import_run_id = import_run_id
        super().__init__(
            f"import run {import_run_id}: its log entry repeats a run the log "
            "does not record before it; nothing of the run was restored. "
            "Restore the log from the newest backup set."
        )


class _NotAnEntryError(ValueError):
    """A complete log line that is not a valid entry; its caller numbers it."""


def _entry_object(line: bytes) -> dict[str, object]:
    """Read a line as a JSON object holding exactly an entry's fields."""
    try:
        parsed: object = json.loads(line)
    except ValueError:
        raise _NotAnEntryError from None
    if not isinstance(parsed, dict) or set(parsed) != _ENTRY_FIELDS:
        raise _NotAnEntryError
    entry: dict[str, object] = {str(field): value for field, value in parsed.items()}
    # A bool is an int to Python, but `true` is not format 1.
    if type(entry["format"]) is not int or entry["format"] != IMPORT_LOG_FORMAT:
        raise _NotAnEntryError
    return entry


def _text(entry: Mapping[str, object], field: str) -> str:
    """Return a field that must be a string."""
    value = entry[field]
    if not isinstance(value, str):
        raise _NotAnEntryError
    return value


def _one_of[T](entry: Mapping[str, object], field: str, values: Mapping[str, T]) -> T:
    """Return a string field that must be one of a few values."""
    try:
        return values[_text(entry, field)]
    except KeyError:
        raise _NotAnEntryError from None


def _date(entry: Mapping[str, object], field: str) -> date:
    """Return a field that must be an ISO date."""
    try:
        return date.fromisoformat(_text(entry, field))
    except ValueError:
        raise _NotAnEntryError from None


def _started_at(entry: Mapping[str, object]) -> datetime:
    """Return `started_at`, which Bronze always writes with its offset."""
    try:
        started_at = datetime.fromisoformat(_text(entry, "started_at"))
    except ValueError:
        raise _NotAnEntryError from None
    if started_at.tzinfo is None:
        raise _NotAnEntryError
    return started_at


def _repeat_of(entry: Mapping[str, object], outcome: str) -> str | None:
    """Return the repeat link, which a repeat has and no other run does."""
    if outcome != "repeat":
        if entry["repeat_of"] is not None:
            raise _NotAnEntryError
        return None
    return _text(entry, "repeat_of")


def _logged_run(line: bytes) -> tuple[ImportRun, str]:
    """Read one complete log line as the run it mirrors and its archive path."""
    entry = _entry_object(line)
    payload_id = _text(entry, "payload_sha256")
    if _SHA256.fullmatch(payload_id) is None:
        raise _NotAnEntryError
    archive_path = _text(entry, "archive_path")
    outcome = _one_of(entry, "outcome", _OUTCOMES)
    run = ImportRun(
        import_run_id=_text(entry, "import_run_id"),
        payload_id=payload_id,
        declared_account_id=_text(entry, "account_id"),
        source_format=_text(entry, "source_format"),
        original_filename=archive_path.rsplit("/", 1)[-1],
        exported_on=_date(entry, "exported_on"),
        exported_on_source=_one_of(entry, "exported_on_source", _DATE_SOURCES),
        covers_from=_date(entry, "covers_from"),
        covers_through=_date(entry, "covers_through"),
        started_at=_started_at(entry),
        outcome=outcome,
        repeat_of=_repeat_of(entry, outcome),
    )
    # The path must be one the import itself could have archived the run at,
    # which also keeps it inside the run's account folder.
    if archive_path not in archive_candidates(run):
        raise _NotAnEntryError
    return run, archive_path


def _read_log(profile: Profile) -> tuple[tuple[ImportRun, str], ...]:
    """Read every complete entry of the log, refusing it whole if one is invalid.

    A final line without its line feed was cut off by a crash and is not an
    entry yet, so it is left out. A missing log records no history.
    """
    if not profile.import_log_file.exists():
        return ()
    lines = profile.import_log_file.read_bytes().split(b"\n")[:-1]
    logged = []
    run_ids: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        try:
            run, archive_path = _logged_run(line)
        except _NotAnEntryError:
            raise ImportLogInvalidError(line_number) from None
        if run.import_run_id in run_ids:
            raise ImportLogInvalidError(line_number)
        run_ids.add(run.import_run_id)
        logged.append((run, archive_path))
    return tuple(logged)


def _archived_export(profile: Profile, run: ImportRun, archive_path: str) -> bytes:
    """Read a logged run's archived export, proven by the hash its entry names."""
    try:
        content = profile.archive_file(archive_path).read_bytes()
    except FileNotFoundError:
        raise ArchivedExportMissingError(run.import_run_id) from None
    if sha256(content).hexdigest() != run.payload_id:
        raise ArchivedExportMismatchError(run.import_run_id)
    return content


def _check_prefix(
    held: tuple[ImportRun, ...], logged: tuple[tuple[ImportRun, str], ...]
) -> None:
    """Refuse unless Bronze holds exactly the log's first runs, as logged."""
    logged_runs = {run.import_run_id: run for run, _ in logged}
    for position, run in enumerate(held):
        logged_run = logged_runs.get(run.import_run_id)
        if logged_run is not None and logged_run != run:
            raise RunConflictError(run.import_run_id)
        if position >= len(logged) or logged[position][0] != run:
            raise NotALogPrefixError


def replay_import_log(lock: WriterLock) -> tuple[ImportRun, ...]:
    """Restore every logged run Bronze lacks; return the runs restored.

    Bronze must hold exactly the log's first runs, as logged; the rest are
    restored in log order, each with its payload and derived cache at once.
    """
    profile = lock.profile
    logged = _read_log(profile)
    restored = []
    with BronzeStore(profile) as store:
        held = store.import_runs()
        _check_prefix(held, logged)
        recorded = {run.import_run_id for run in held}
        for run, archive_path in logged[len(held) :]:
            if run.repeat_of is not None and run.repeat_of not in recorded:
                raise UnknownRepeatOfError(run.import_run_id)
            content = _archived_export(profile, run, archive_path)
            store.restore_import_run(run, content)
            recorded.add(run.import_run_id)
            restored.append(run)
    return tuple(restored)
