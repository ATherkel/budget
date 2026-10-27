# Copyright 2026 Therkel
"""The `restore` application operation: put a whole profile back from one set.

Every store a backup set lists is restored together, into a profile that has
no stores; a store is never restored beside live ones (`operations.md`,
*Backup and Restore*).
"""

import shutil

from budget.backups import BackupSet, complete_backup_sets, set_store_files
from budget.locking import WriterLock


def _selected(sets: tuple[BackupSet, ...], name: str | None) -> BackupSet:
    """Return the set named `name`, or the newest when no name is given."""
    if name is None:
        return sets[0]
    return next(found for found in sets if found.name == name)


def restore(lock: WriterLock, name: str | None = None) -> BackupSet:
    """Restore every store of one complete set; return the set.

    `name` selects the set; without it, the newest complete set is taken.
    """
    profile = lock.profile
    selected = _selected(complete_backup_sets(profile), name)
    for store in set_store_files(selected):
        shutil.copyfile(selected.path / store, profile.stores / store)
    return selected
