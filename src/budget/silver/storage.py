# Copyright 2026 Therkel
"""The Silver stage store: its file, its migrations and its guards.

The runner, the numbered SQL files under `budget/migrations/silver/` inside the
installed package, and every refusal around them are shared with Bronze
(`budget.sqlstore`). This module names the Silver stage, re-exports the shared
refusals under the stage's own module, and will hold the persistence-level
money conversion.
"""

import sqlite3
from typing import Final

from budget.profiles import Profile
from budget.sqlstore import (
    BUSY_TIMEOUT_MS,
    ForeignKeyViolationError,
    MigrationRequiredError,
    MigrationResourceError,
    ProductionMigrationBlockedError,
    StoreBusyError,
    StoreError,
    StoreIdentityError,
    StoreNotFoundError,
    UnsupportedSQLiteVersionError,
    UnsupportedStoreVersionError,
    UnversionedStoreError,
    require_migration_allowed,
)

SILVER_STAGE: Final = "silver"

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
    raise NotImplementedError


def open_silver_connection(profile: Profile) -> sqlite3.Connection:
    """Open an existing Silver store, refusing anything it cannot vouch for."""
    raise NotImplementedError
