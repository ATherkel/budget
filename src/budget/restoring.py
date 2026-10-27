# Copyright 2026 Therkel
"""The `restore` application operation: put a whole profile back from one set.

Every store a backup set lists is restored together, into a profile that has
no stores; a store is never restored beside live ones (`operations.md`,
*Backup and Restore*).
"""

import shutil

from budget.backups import BackupSet, complete_backup_sets, set_store_files
from budget.locking import WriterLock


def restore(lock: WriterLock) -> BackupSet:
    """Restore every store of the newest complete set; return the set."""
    profile = lock.profile
    newest = complete_backup_sets(profile)[0]
    for name in set_store_files(newest):
        shutil.copyfile(newest.path / name, profile.stores / name)
    return newest
