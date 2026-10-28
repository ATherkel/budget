# Copyright 2026 Therkel
"""The `dev refresh` application operation: production's data for development.

Development reads production only through a backup set (ADR-015). Plain
`dev refresh` restores production's newest complete set into development's
`upstream` folder, read-only, and leaves development's own stores and
inputs alone (`operations.md`, *Development diverges from a stage*).
"""

import shutil
import stat
from pathlib import Path
from typing import Final

from budget.backups import BackupSet, complete_sets_in, set_store_files
from budget.locking import WriterLock

# Development's folder of production's restored stores.
UPSTREAM_FOLDER: Final = "upstream"


def refresh(lock: WriterLock) -> BackupSet:
    """Restore production's newest complete set into `upstream`, read-only."""
    profile = lock.profile
    newest = complete_sets_in(Path(str(profile.upstream_backups)))[0]
    upstream = profile.stores / UPSTREAM_FOLDER
    upstream.mkdir(exist_ok=True)
    for store in set_store_files(newest).values():
        copy = upstream / store
        shutil.copyfile(newest.path / store, copy)
        copy.chmod(stat.S_IREAD)
    return newest
