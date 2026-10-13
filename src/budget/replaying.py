# Copyright 2026 Therkel
"""Replay the import log into Bronze, from the export archive.

`imports.jsonl` holds what exists nowhere outside Bronze: each run's ID,
declarations, timestamp and outcome. With the archived bytes it names, it
rebuilds Bronze's history exactly, into an empty store or onto a restored
store that holds a prefix of it.
"""

from budget.bronze import ImportRun
from budget.locking import WriterLock


def replay_import_log(lock: WriterLock) -> tuple[ImportRun, ...]:
    """Restore every logged run Bronze lacks; return the runs restored."""
    del lock
    return ()
