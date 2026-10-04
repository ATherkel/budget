# Copyright 2026 Therkel
"""The Bronze stage store: its file, its migrations and its guards.

The runner, the numbered SQL files under `budget/migrations/bronze/` inside the
installed package, and every refusal around them are shared with the other
stages (`budget.sqlstore`). This module only names the Bronze stage: its
`stage` value, its file through the profile, and the label its refusals use.
"""

import sqlite3
from pathlib import Path
from typing import Final

from budget.profiles import PRODUCTION_PROFILE_NAME, Profile

# Re-exported so `budget.bronze.storage` keeps naming what it always named.
from budget.sqlstore import (
    BUSY_TIMEOUT_MS,
    SQLITE_VERSION_FLOOR,
    ForeignKeyViolationError,
    MigrationRequiredError,
    MigrationResourceError,
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
    require_migration_allowed,
)

# The refusals are shared between the stage stores now, so the old base name
# stays as an alias rather than a second, incompatible exception.
BronzeStorageError = StoreError

BRONZE_STAGE: Final = "bronze"
_MIGRATIONS_FOLDER: Final = (
    Path(__file__).resolve().parent.parent / "migrations" / "bronze"
)

__all__ = [
    "BRONZE_STAGE",
    "BUSY_TIMEOUT_MS",
    "PRODUCTION_PROFILE_NAME",
    "SQLITE_VERSION_FLOOR",
    "BronzeStorageError",
    "ForeignKeyViolationError",
    "MigrationRequiredError",
    "MigrationResourceError",
    "ProductionMigrationBlockedError",
    "StoreBusyError",
    "StoreError",
    "StoreIdentityError",
    "StoreNotFoundError",
    "UnsupportedSQLiteVersionError",
    "UnsupportedStoreVersionError",
    "UnversionedStoreError",
    "migrate_bronze",
    "open_bronze_connection",
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


def migrate_bronze(profile: Profile) -> None:
    """Create or upgrade the Bronze store that one profile names.

    The production profile is refused before any folder or file is touched.
    """
    migrate_store(bronze_stage(profile))


def open_bronze_connection(profile: Profile) -> sqlite3.Connection:
    """Open an existing Bronze store, refusing anything it cannot vouch for."""
    return open_store_connection(bronze_stage(profile))
