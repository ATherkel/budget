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
    LostStoreError,
    back_up,
    complete_backup_sets,
    hold_for_recovery,
    holds_store,
    release_recovery_sets,
    require_supported_stores,
)
from budget.bronze.storage import BRONZE_STAGE, bronze_stage
from budget.importing import ImportLogAheadOfBronzeError, ImportLogDamagedError
from budget.locking import WriterLock
from budget.profiles import PRODUCTION_PROFILE_NAME, Profile
from budget.silver.storage import SILVER_STAGE, silver_stage
from budget.sqlstore import (
    NewStoreRequiredError,
    StageStore,
    StoreError,
    is_started,
    migrate_store,
)
from budget.sqlstore import (
    require_migration_allowed as require_store_migration_allowed,
)


class RestoreInsteadError(RuntimeError):
    """A new production store was asked for, but backup sets could restore one.

    A complete backup set holding the store means production had one; an
    empty one started in its place would be backed up over them in time.
    """

    def __init__(self, label: str) -> None:
        """Say why nothing was started, and what to do instead."""
        super().__init__(
            "the backups folder holds complete backup sets of this profile, so "
            f"its {label} store must be restored from the newest that holds "
            "one, not started anew; nothing was written"
        )


class MigratedWithoutBackupError(RuntimeError):
    """The stores were migrated, but no backup set of them could follow.

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
    LostStoreError,
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
    another stage's change. Production migrates a later stage only beside a
    Bronze store, since every backup set holds Bronze: a store started
    without one could never be backed up.
    """
    bronze = bronze_stage(profile)
    if (
        profile.name == PRODUCTION_PROFILE_NAME
        and BRONZE_STAGE not in stages
        and not bronze.path.exists()
    ):
        # Checked first, so the advice is the step that works: a later stage
        # would be refused anew until Bronze has a store.
        require_store_migration_allowed(bronze)
    for store in _stage_stores(profile, stages):
        require_store_migration_allowed(store, new_store=new_store)


def _require_bronze_beside(profile: Profile, stages: Collection[str]) -> None:
    """Refuse a production stage after Bronze where Bronze's store is not started.

    `require_migration_allowed` refuses a missing file before the lock; this
    reads the file under it, so one an interrupted start left empty is
    refused too.
    """
    bronze = bronze_stage(profile)
    if BRONZE_STAGE not in stages and not is_started(bronze):
        raise NewStoreRequiredError(bronze.label, bronze.stage)


def _require_every_store_new(stores: list[StageStore]) -> None:
    """Refuse new production stores where some asked for are started already.

    The runner refuses an existing store only once it reaches it, after the
    stages before it were started; a store started that way would have no
    backup set after it. Where none is started, each is started in turn. A
    file an interrupted start left empty does not count: the runner starts
    it again. The refusal names the first store still to start, and the
    `--stage` that starts it alone.
    """
    missing = [store for store in stores if not is_started(store)]
    if missing and len(missing) < len(stores):
        raise NewStoreRequiredError(missing[0].label, missing[0].stage)


def _require_nothing_to_restore(profile: Profile, stores: list[StageStore]) -> None:
    """Refuse a new store where a complete backup set holds one to restore.

    A set written before backups covered Silver holds no Silver store, so it
    never stands in the way of starting one.
    """
    sets = complete_backup_sets(profile)
    for store in stores:
        if not is_started(store) and any(
            holds_store(backup, store.stage) for backup in sets
        ):
            raise RestoreInsteadError(store.label)


def migrate_profile(
    lock: WriterLock,
    *,
    stages: Collection[str] = MIGRATED_STAGES,
    new_store: bool = False,
    clock: Callable[[], datetime] = _utc_now,
) -> None:
    """Create or upgrade the locked profile's stores for `stages`.

    Bronze is migrated before Silver, each in its own transaction. In
    production, the first store found to need a change takes one backup set
    of every store before it changes, held for recovery; a set follows once
    every stage is migrated, if any changed. `new_store` asks for a new
    production store where none exists. `clock` names each backup set.
    """
    profile = lock.profile
    stores = _stage_stores(profile, stages)
    if profile.name != PRODUCTION_PROFILE_NAME:
        for store in stores:
            migrate_store(store)
        return
    require_supported_stores(profile)
    _require_bronze_beside(profile, stages)
    if new_store:
        _require_nothing_to_restore(profile, stores)
        _require_every_store_new(stores)

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
