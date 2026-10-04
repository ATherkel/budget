# Copyright 2026 Therkel
"""The Silver stage store: its file, its migrations and its guards.

The runner, the numbered SQL files under `budget/migrations/silver/` inside the
installed package, and every refusal around them are shared with Bronze
(`budget.sqlstore`). This module names the Silver stage, re-exports the shared
refusals under the stage's own module, and will hold the persistence-level
money conversion.
"""

import sqlite3
from pathlib import Path
from typing import Final

from budget.profiles import Profile
from budget.sqlstore import (
    BUSY_TIMEOUT_MS,
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

SILVER_STAGE: Final = "silver"
_MIGRATIONS_FOLDER: Final = (
    Path(__file__).resolve().parent.parent / "migrations" / "silver"
)

__all__ = [
    "BUSY_TIMEOUT_MS",
    "SILVER_STAGE",
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
    "migrate_silver",
    "open_silver_connection",
    "require_migration_allowed",
]


def migrate_silver(profile: Profile) -> None:
    """Create or upgrade the Silver store that one profile names.

    The production profile is refused before any folder or file is touched.
    """
    migrate_store(silver_stage(profile))


def silver_stage(profile: Profile) -> StageStore:
    """Name the Silver store one profile describes."""
    return StageStore(
        profile=profile,
        stage=SILVER_STAGE,
        label="Silver",
        path=profile.silver_store,
        migrations=_MIGRATIONS_FOLDER,
    )


def open_silver_connection(profile: Profile) -> sqlite3.Connection:
    """Open an existing Silver store, refusing anything it cannot vouch for."""
    return open_store_connection(silver_stage(profile))
