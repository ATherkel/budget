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


def replay_import_log(lock: WriterLock) -> tuple[ImportRun, ...]:
    """Restore every logged run Bronze lacks; return the runs restored."""
    profile = lock.profile
    lines = profile.import_log_file.read_bytes().split(b"\n")[:-1]
    restored = []
    with BronzeStore(profile) as store:
        held = {run.import_run_id for run in store.import_runs()}
        for line in lines:
            entry = json.loads(line)
            run = _logged_run(entry)
            if run.import_run_id in held:
                continue
            content = _archived_export(profile, run, entry["archive_path"])
            store.restore_import_run(run, content)
            restored.append(run)
    return tuple(restored)
