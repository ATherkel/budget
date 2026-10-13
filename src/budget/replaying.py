# Copyright 2026 Therkel
"""Replay the import log into Bronze, from the export archive.

`imports.jsonl` holds what exists nowhere outside Bronze: each run's ID,
declarations, timestamp and outcome. With the archived bytes it names, it
rebuilds Bronze's history exactly, into an empty store or onto a restored
store that holds a prefix of it.
"""

import json
from datetime import date, datetime
from typing import Any

from budget.bronze import BronzeStore, ImportRun
from budget.locking import WriterLock


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


def replay_import_log(lock: WriterLock) -> tuple[ImportRun, ...]:
    """Restore every logged run Bronze lacks; return the runs restored."""
    profile = lock.profile
    lines = profile.import_log_file.read_bytes().split(b"\n")[:-1]
    restored = []
    with BronzeStore(profile) as store:
        for line in lines:
            entry = json.loads(line)
            run = _logged_run(entry)
            content = profile.archive_file(entry["archive_path"]).read_bytes()
            store.restore_import_run(run, content)
            restored.append(run)
    return tuple(restored)
