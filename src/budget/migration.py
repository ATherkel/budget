# Copyright 2026 Therkel
"""Migrating a profile's stores, with production's backups around it.

In production, a migration that changes an existing store begins only once a
verified backup set of it is published, and a backup set follows every
migration that changed anything. Development and test profiles migrate
without backups: only production writes backup sets.
"""

from collections.abc import Callable, Collection
from datetime import UTC, datetime
from typing import Final

from budget.backups import (
    BackupSet,
    BackupVerificationError,
    BackupWriteError,
    back_up,
    complete_backup_sets,
    hold_for_recovery,
    release_recovery_sets,
    require_supported_stores,
)
from budget.bronze.storage import BRONZE_STAGE, bronze_stage
from budget.importing import ImportLogAheadOfBronzeError, ImportLogDamagedError
from budget.locking import WriterLock
from budget.profiles import PRODUCTION_PROFILE_NAME, Profile
from budget.silver.storage import SILVER_STAGE, silver_stage
from budget.sqlstore import StageStore, StoreError, migrate_store
from budget.sqlstore import (
    require_migration_allowed as require_store_migration_allowed,
)


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
            "the stores were migrated, but no backup set of them could be "
            f"written after: {reason}. Put that right, then run `budget backup`"
        )


# Each stage `migrate` creates or upgrades, in the order it does so.
_STAGE_STORES: Final[dict[str, Callable[[Profile], StageStore]]] = {
    BRONZE_STAGE: bronze_stage,
    SILVER_STAGE: silver_stage,
}
MIGRATED_STAGES: Final = tuple(_STAGE_STORES)
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


def _stage_stores(profile: Profile, stages: Collection[str]) -> list[StageStore]:
    """Name the profile's store for each of `stages`, Bronze before Silver."""
    return [
        stage_store(profile)
        for stage, stage_store in _STAGE_STORES.items()
        if stage in stages
    ]


def require_migration_allowed(
    profile: Profile,
    *,
    stages: Collection[str] = MIGRATED_STAGES,
    new_store: bool = False,
) -> None:
    """Refuse a migration of `stages` this interpreter or profile cannot run.

    These checks touch no folder or file, so a command can run them before it
    takes the profile's writer lock. A production profile without one of the
    stores is refused unless a new store is asked for: a missing store may be
    a lost one, which a backup set must restore instead. Every stage is
    checked before any is migrated, so one stage's refusal never follows
    another stage's change.
    """
    for store in _stage_stores(profile, stages):
        require_store_migration_allowed(store, new_store=new_store)


def migrate_profile(
    lock: WriterLock,
    *,
    stages: Collection[str] = MIGRATED_STAGES,
    new_store: bool = False,
    clock: Callable[[], datetime] = _utc_now,
) -> None:
    """Create or upgrade the locked profile's stores for `stages`.

    Bronze is migrated before Silver. `new_store` asks for a new production
    store where none exists. `clock` names each backup set.
    """
    profile = lock.profile
    stores = _stage_stores(profile, stages)
    if profile.name != PRODUCTION_PROFILE_NAME:
        for store in stores:
            migrate_store(store)
        return
    require_supported_stores(profile)
    if (
        new_store
        and not profile.bronze_store.exists()
        and complete_backup_sets(profile)
    ):
        raise RestoreInsteadError

    taken: list[BackupSet] = []

    def back_up_first() -> None:
        # One set, taken before the first store changes, covers every store.
        # Held until a migration succeeds, so retention keeps the set a
        # failed or interrupted one needs.
        if not taken:
            taken.append(back_up(lock, now=clock()))
            hold_for_recovery(lock, taken[0])

    changed = False
    for store in stores:
        migrated = migrate_store(
            store, new_store=new_store, before_migrating=back_up_first
        )
        changed = changed or migrated
    if not changed:
        return
    try:
        back_up(lock, now=clock())
    except _BACKUP_FAILURES as error:
        raise MigratedWithoutBackupError(error) from error
    release_recovery_sets(lock)
