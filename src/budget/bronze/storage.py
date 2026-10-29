# Copyright 2026 Therkel
"""The Bronze stage store: its file, its migrations and its guards.

Only the store runner creates or changes the schema: through
`migrate_bronze`, or through `budget migrate` (`budget.migration`), which
backs a production store up first. Opening a store never does: it refuses a
file that is missing, belongs to another profile or stage, or is at a schema
version this code does not know. The numbered SQL lives in
`budget/migrations/bronze/` inside the installed package, and each stage
keeps its own `PRAGMA user_version`. The runner and every refusal around it come
from the generic store runner (`budget.sqlstore`); this module names the
Bronze stage and re-exports its refusals.
"""

import sqlite3
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
    open_store_snapshot,
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
    "open_bronze_snapshot",
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


def migrate_bronze(profile: Profile) -> None:
    """Create or upgrade the Bronze store that one profile names.

    The production profile is refused before any folder or file is touched:
    it is migrated only by `budget migrate`, which backs the store up first.
    """
    migrate_store(bronze_stage(profile))


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
