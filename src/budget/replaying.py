# Copyright 2026 Therkel
"""Replay the import log into Bronze, from the export archive.

`imports.jsonl` holds what exists nowhere outside Bronze: each run's ID,
declarations, timestamp and outcome. With the archived bytes it names, it
rebuilds Bronze's history exactly, into an empty store or onto a restored
store that holds a prefix of it.
"""

import json
from datetime import date, datetime
from hashlib import sha256
from typing import Any

from budget.bronze import BronzeStore, ImportRun
from budget.locking import WriterLock
from budget.profiles import Profile


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


def _logged_run(entry: dict[str, Any]) -> ImportRun:
    """Read one log entry back as the run it mirrors."""
    archive_path = str(entry["archive_path"])
    return ImportRun(
        import_run_id=entry["import_run_id"],
        payload_id=entry["payload_sha256"],
        declared_account_id=entry["account_id"],
        source_format=entry["source_format"],
        original_filename=archive_path.rsplit("/", 1)[-1],
        exported_on=date.fromisoformat(entry["exported_on"]),
        exported_on_source=entry["exported_on_source"],
        covers_from=date.fromisoformat(entry["covers_from"]),
        covers_through=date.fromisoformat(entry["covers_through"]),
        started_at=datetime.fromisoformat(entry["started_at"]),
        outcome=entry["outcome"],
        repeat_of=entry["repeat_of"],
    )


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
    lines = profile.import_log_file.read_bytes().split(b"\n")[:-1]
    logged = tuple(
        (_logged_run(entry), str(entry["archive_path"]))
        for entry in map(json.loads, lines)
    )
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
