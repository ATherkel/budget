# Copyright 2026 Therkel
"""The `restore` application operation: put a whole profile back from one set.

Every store a backup set lists is restored together, into a profile that has
no stores; a store is never restored beside live ones (`operations.md`,
*Backup and Restore*).
"""

import shutil
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from typing import Final

from budget.backups import BackupSet, complete_backup_sets, set_store_files
from budget.bronze.storage import bronze_stage
from budget.gold.storage import gold_stage
from budget.locking import WriterLock
from budget.migration import migrate_profile
from budget.profiles import Profile
from budget.silver.storage import silver_stage
from budget.sqlstore import StageStore, StoreError, open_store_snapshot

# Where a restore copies a set's stores before moving them into place.
RESTORE_STAGING: Final = "restore-staging"
_STAGES: Final[dict[str, Callable[[Profile], StageStore]]] = {
    "bronze": bronze_stage,
    "silver": silver_stage,
    "gold": gold_stage,
}


class RestoreWriteError(RuntimeError):
    """The set's stores could not be copied into place: none was restored."""

    def __init__(self, reason: str) -> None:
        """Say why, and that no store came of it."""
        super().__init__(
            f"the backup set could not be restored: {reason}; nothing was restored"
        )


class IncompleteSetError(RuntimeError):
    """The set asked for by name is not complete: nothing was restored.

    A set asked for by name is never swapped for another one.
    """

    def __init__(self, name: str) -> None:
        """Name the set, and say that nothing was restored."""
        super().__init__(
            f"backup set {name} is not complete: it is missing, or a file does "
            "not match the checksum its manifest records; nothing was restored"
        )


class OccupiedProfileError(RuntimeError):
    """The profile still has a store: nothing was restored or deleted.

    A whole profile is restored, never one store beside live ones, and the
    stores already there are the operator's to keep or set aside.
    """

    def __init__(self, names: list[str]) -> None:
        """Name what is in the way, and how to retry."""
        super().__init__(
            f"the stores folder still holds {', '.join(names)}: restore puts "
            "back a whole profile, never a store beside live ones; move every "
            "store out of it, keeping them if they may be needed, then rerun; "
            "nothing was restored"
        )


def _require_no_stores(profile: Profile) -> None:
    """Refuse a profile that has any stage store, touching nothing."""
    stores = (profile.bronze_store, profile.silver_store, profile.gold_store)
    found = [store.name for store in stores if store.exists()]
    if found:
        raise OccupiedProfileError(found)


@dataclass(frozen=True)
class Restored:
    """What `restore` did: the set it restored, and newer sets it passed over."""

    backup: BackupSet
    skipped: tuple[str, ...]


class DamagedStoreError(RuntimeError):
    """A store in the set fails SQLite's integrity check: nothing was restored.

    Its checksum can match while its pages do not, as when the store was
    already damaged when the set was taken.
    """

    def __init__(self, store: str, name: str) -> None:
        """Name the store and the set, and say that nothing was restored."""
        super().__init__(
            f"{store} in backup set {name} fails SQLite's integrity check; "
            "nothing was restored"
        )


def _is_intact(connection: sqlite3.Connection) -> bool:
    """Report whether SQLite's integrity check finds the database sound."""
    try:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError:
        return False
    return [tuple(row) for row in rows] == [("ok",)]


def _require_readable(profile: Profile, backup: BackupSet) -> None:
    """Refuse a set holding a store this code cannot open, touching nothing.

    A store at a schema version this code does not know is a `StoreError`;
    one SQLite finds damaged is a `DamagedStoreError`.
    """
    for stage, name in set_store_files(backup).items():
        path = backup.path / name
        with closing(open_store_snapshot(_STAGES[stage](profile), path)) as store:
            if not _is_intact(store):
                raise DamagedStoreError(name, backup.name)


def _named(profile: Profile, sets: tuple[BackupSet, ...], name: str) -> BackupSet:
    """Return the complete set named `name`, refusing it if it cannot be read."""
    for found in sets:
        if found.name == name:
            _require_readable(profile, found)
            return found
    raise IncompleteSetError(name)


def _newest_readable(
    profile: Profile, sets: tuple[BackupSet, ...]
) -> tuple[BackupSet, tuple[str, ...]]:
    """Return the newest set this code can read, and the newer ones passed over."""
    skipped: list[str] = []
    for index, found in enumerate(sets):
        try:
            _require_readable(profile, found)
        except StoreError:
            if index == len(sets) - 1:
                raise
            skipped.append(found.name)
            continue
        return found, tuple(skipped)
    raise IndexError(len(sets))


def _copy_whole(profile: Profile, backup: BackupSet, stores: Iterable[str]) -> None:
    """Copy every store of a set into the stores folder, or none of them.

    Each store is copied into a staging folder beside the live ones first,
    and moved into place only once every copy is made, so a copy that fails
    leaves no store a retry would find in its way.
    """
    staging = profile.stores / RESTORE_STAGING
    try:
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        for store in stores:
            shutil.copyfile(backup.path / store, staging / store)
        for staged in staging.iterdir():
            staged.replace(profile.stores / staged.name)
    except OSError as error:
        raise RestoreWriteError(error.strerror or type(error).__name__) from None
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def restore(lock: WriterLock, name: str | None = None) -> Restored:
    """Restore every store of one complete set; report what was restored.

    `name` selects the set; without it, the newest complete set this code
    can read is taken, and every newer set is passed over.
    """
    profile = lock.profile
    _require_no_stores(profile)
    sets = complete_backup_sets(profile)
    if name is None:
        selected, skipped = _newest_readable(profile, sets)
    else:
        selected, skipped = _named(profile, sets, name), ()
    stores = set_store_files(selected)
    _copy_whole(profile, selected, stores.values())
    # A store the set holds at an older version is upgraded as `migrate`
    # upgrades a live one, backed up before and after.
    migrate_profile(lock, stages=tuple(stores))
    return Restored(backup=selected, skipped=skipped)
