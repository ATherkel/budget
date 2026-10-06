# Copyright 2026 Therkel
"""Migrating a profile's stores, with production's backups around it.

In production, a migration that changes an existing store begins only once a
verified backup set of it is published, and a backup set follows every
migration that changed anything. Development and test profiles migrate
without backups: only production writes backup sets.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Final

from budget.backups import (
    BackupVerificationError,
    BackupWriteError,
    back_up,
    complete_backup_sets,
    hold_for_recovery,
    release_recovery_sets,
    require_supported_stores,
)
from budget.bronze import migrate_bronze
from budget.importing import ImportLogAheadOfBronzeError, ImportLogDamagedError
from budget.locking import WriterLock
from budget.profiles import PRODUCTION_PROFILE_NAME
from budget.sqlstore import StoreError


class RestoreInsteadError(RuntimeError):
    """A new production store was asked for, but backup sets could restore one.

    Complete backup sets mean production had a store; an empty one started
    in its place would be backed up over them in time.
    """

    def __init__(self) -> None:
        """Say why nothing was started, and what to do instead."""
        super().__init__(
            "the backups folder holds complete backup sets of this profile, so "
            "its Bronze store must be restored from the newest, not started "
            "anew; nothing was written"
        )


class MigratedWithoutBackupError(RuntimeError):
    """The store was migrated, but no backup set of it could follow.

    The migration is committed. The set taken before it stays held for
    recovery, and `budget backup` writes the missing set once its problem is
    put right.
    """

    def __init__(self, reason: Exception) -> None:
        """Say what happened, what did not, and what to run."""
        super().__init__(
            "the Bronze store was migrated, but no backup set of it could be "
            f"written after: {reason}. Put that right, then run `budget backup`"
        )


# Every way a backup set can fail to be written once the store is migrated.
_BACKUP_FAILURES: Final = (
    BackupWriteError,
    BackupVerificationError,
    StoreError,
    ImportLogDamagedError,
    ImportLogAheadOfBronzeError,
)


def _utc_now() -> datetime:
    """Read the clock, in UTC."""
    return datetime.now(UTC)


def migrate_profile(
    lock: WriterLock,
    *,
    new_store: bool = False,
    clock: Callable[[], datetime] = _utc_now,
) -> None:
    """Create or upgrade the locked profile's stores: Bronze, for now.

    `new_store` asks for a new production store where none exists. `clock`
    names each backup set.
    """
    profile = lock.profile
    if profile.name != PRODUCTION_PROFILE_NAME:
        migrate_bronze(profile)
        return
    require_supported_stores(profile)
    if (
        new_store
        and not profile.bronze_store.exists()
        and complete_backup_sets(profile)
    ):
        raise RestoreInsteadError

    def back_up_first() -> None:
        # Held until a migration succeeds, so retention keeps the set a
        # failed or interrupted one needs.
        hold_for_recovery(lock, back_up(lock, now=clock()))

    if not migrate_bronze(profile, new_store=new_store, before_migrating=back_up_first):
        return
    try:
        back_up(lock, now=clock())
    except _BACKUP_FAILURES as error:
        raise MigratedWithoutBackupError(error) from error
    release_recovery_sets(lock)
