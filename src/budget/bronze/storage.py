# Copyright 2026 Therkel
"""The Bronze stage store: its file, its migrations and its guards.

Only `migrate_bronze` creates or changes the schema. Opening a store never
does: it refuses a file that is missing, belongs to another profile or stage,
or is at a schema version this code does not know. The numbered SQL lives in
`budget/migrations/bronze/` inside the installed package, and each stage keeps
its own `PRAGMA user_version`. The runner and every refusal around it come
from the generic store runner (`budget.sqlstore`); this module names the
Bronze stage and re-exports its refusals.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Final

from budget.profiles import Profile
from budget.sqlstore import (
    BUSY_TIMEOUT_MS,
    SQLITE_VERSION_FLOOR,
    ForeignKeyViolationError,
    MigrationRequiredError,
    MigrationResourceError,
    NewStoreRefusedError,
    NewStoreRequiredError,
    ProductionMigrationBlockedError,
    StageStore,
    StoreBusyError,
    StoreError,
    StoreIdentityError,
    StoreNotFoundError,
    UnsupportedSQLiteVersionError,
    UnsupportedStoreVersionError,
    UnversionedStoreError,
    migrate_store,
    open_store_connection,
    open_store_for_backup,
    open_store_snapshot,
)
from budget.sqlstore import (
    require_migration_allowed as require_store_migration_allowed,
)

BRONZE_STAGE: Final = "bronze"
_MIGRATIONS_FOLDER: Final = (
    Path(__file__).resolve().parent.parent / "migrations" / "bronze"
)

__all__ = [
    "BRONZE_STAGE",
    "BUSY_TIMEOUT_MS",
    "SQLITE_VERSION_FLOOR",
    "ForeignKeyViolationError",
    "MigrationRequiredError",
    "MigrationResourceError",
    "NewStoreRefusedError",
    "NewStoreRequiredError",
    "ProductionMigrationBlockedError",
    "StoreBusyError",
    "StoreError",
    "StoreIdentityError",
    "StoreNotFoundError",
    "UnsupportedSQLiteVersionError",
    "UnsupportedStoreVersionError",
    "UnversionedStoreError",
    "bronze_stage",
    "migrate_bronze",
    "open_bronze_connection",
    "open_bronze_for_backup",
    "open_bronze_snapshot",
    "require_migration_allowed",
]


def bronze_stage(profile: Profile) -> StageStore:
    """Name the Bronze store one profile describes."""
    return StageStore(
        profile=profile,
        stage=BRONZE_STAGE,
        label="Bronze",
        path=profile.bronze_store,
        migrations=_MIGRATIONS_FOLDER,
    )


def require_migration_allowed(profile: Profile, *, new_store: bool = False) -> None:
    """Refuse a Bronze migration this interpreter or profile cannot run.

    These checks touch no folder or file, so a command can run them before it
    takes the profile's writer lock. A production profile without a Bronze
    store is refused unless a new store is asked for: a missing store may be
    a lost one, which a backup set must restore instead.
    """
    require_store_migration_allowed(bronze_stage(profile), new_store=new_store)


def migrate_bronze(
    profile: Profile,
    *,
    new_store: bool = False,
    before_migrating: Callable[[], object] | None = None,
) -> bool:
    """Create or upgrade the Bronze store that one profile names.

    Returns whether a migration was applied. `before_migrating` runs once the
    store is found to need one and before anything changes, unless the store
    is new. Production is migrated only with it, which is how `budget migrate`
    backs the store up first, and is refused before anything is touched
    without it. A production store is started only with `new_store`, which is
    refused where one exists; other profiles start a missing store freely.
    """
    return migrate_store(
        bronze_stage(profile),
        new_store=new_store,
        before_migrating=before_migrating,
    )


def open_bronze_for_backup(profile: Profile) -> sqlite3.Connection:
    """Open the profile's live Bronze store to copy it into a backup set.

    Unlike `open_bronze_connection`, a store older than the code is opened:
    production backs a store up before migrating it. The caller only reads.
    """
    return open_store_for_backup(bronze_stage(profile))


def open_bronze_snapshot(profile: Profile, path: Path) -> sqlite3.Connection:
    """Open a backup snapshot of the profile's Bronze store, read-only.

    The snapshot is opened `immutable`, so reading it never writes a WAL or
    shared-memory file beside it. It must be this profile's Bronze store at a
    schema version this code knows; a snapshot taken before a migration may
    be older than the code.
    """
    return open_store_snapshot(bronze_stage(profile), path)


def open_bronze_connection(profile: Profile) -> sqlite3.Connection:
    """Open an existing Bronze store, refusing anything it cannot vouch for."""
    return open_store_connection(bronze_stage(profile))
