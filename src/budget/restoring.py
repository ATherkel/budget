# Copyright 2026 Therkel
"""The `restore` application operation: put a whole profile back from one set.

Every store a backup set lists is restored together, into a profile that has
no stores; a store is never restored beside live ones (`operations.md`,
*Backup and Restore*).
"""

import shutil
from collections.abc import Callable
from contextlib import closing
from typing import Final

from budget.backups import BackupSet, complete_backup_sets, set_store_files
from budget.bronze.storage import bronze_stage
from budget.gold.storage import gold_stage
from budget.locking import WriterLock
from budget.profiles import Profile
from budget.silver.storage import silver_stage
from budget.sqlstore import StageStore, open_store_snapshot

_STAGES: Final[dict[str, Callable[[Profile], StageStore]]] = {
    "bronze": bronze_stage,
    "silver": silver_stage,
    "gold": gold_stage,
}


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


def _selected(sets: tuple[BackupSet, ...], name: str | None) -> BackupSet:
    """Return the set named `name`, or the newest when no name is given."""
    if name is None:
        return sets[0]
    for found in sets:
        if found.name == name:
            return found
    raise IncompleteSetError(name)


def _require_readable(profile: Profile, backup: BackupSet) -> None:
    """Refuse a set holding a store this code cannot open, touching nothing."""
    for stage, name in set_store_files(backup).items():
        with closing(open_store_snapshot(_STAGES[stage](profile), backup.path / name)):
            pass


def restore(lock: WriterLock, name: str | None = None) -> BackupSet:
    """Restore every store of one complete set; return the set.

    `name` selects the set; without it, the newest complete set is taken.
    """
    profile = lock.profile
    _require_no_stores(profile)
    selected = _selected(complete_backup_sets(profile), name)
    _require_readable(profile, selected)
    for store in set_store_files(selected).values():
        shutil.copyfile(selected.path / store, profile.stores / store)
    return selected
