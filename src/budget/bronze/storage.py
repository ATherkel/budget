# Copyright 2026 Therkel
"""Creating, upgrading and opening the Bronze store file.

Only `migrate_bronze` creates or changes the schema. Opening a store never
does: it refuses a file that is missing, belongs to another profile or stage,
or is at a schema version this code does not know. The numbered SQL lives in
`budget/migrations/bronze/` inside the installed package, next to the runner
that applies it, and each stage keeps its own `PRAGMA user_version`.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from budget.profiles import Profile

SQLITE_VERSION_FLOOR: Final = (3, 51, 3)
BRONZE_STAGE: Final = "bronze"
PRODUCTION_PROFILE_NAME: Final = "production"
BUSY_TIMEOUT_MS: Final = 5000


class BronzeStorageError(RuntimeError):
    """A refusal that comes from the store's file or runtime, not its content."""


class UnsupportedSQLiteVersionError(BronzeStorageError):
    """The SQLite in this interpreter is below the store's version floor."""

    def __init__(self, version: tuple[int, ...]) -> None:
        """Name the measured version and the floor."""
        measured = ".".join(str(part) for part in version)
        floor = ".".join(str(part) for part in SQLITE_VERSION_FLOOR)
        super().__init__(f"SQLite {measured} is below the required {floor}")


class ProductionMigrationBlockedError(BronzeStorageError):
    """Production migration waits for the backup and command work."""

    def __init__(self) -> None:
        """State what is missing, without naming any path."""
        super().__init__(
            "the production profile cannot be migrated yet: production "
            "migration waits for the backup and command work in issue #120"
        )


class StoreNotFoundError(BronzeStorageError):
    """No store file exists at the profile's path."""

    def __init__(self, path: Path) -> None:
        """Name the path that has no store."""
        super().__init__(f"no Bronze store at {path}: migrate the profile first")


class UnversionedStoreError(BronzeStorageError):
    """An existing store carries tables but no schema version."""

    def __init__(self, path: Path) -> None:
        """Keep the bytes and ask for a deliberate migration."""
        super().__init__(
            f"{path} is an existing store without a schema version; it is not "
            "adopted automatically. Keep the file and migrate it deliberately."
        )


class StoreIdentityError(BronzeStorageError):
    """The store's recorded profile or stage is not the one being opened."""

    def __init__(self, path: Path, detail: str) -> None:
        """Name the store and what did not match."""
        super().__init__(f"{path} cannot be opened: {detail}")


class MigrationRequiredError(BronzeStorageError):
    """The store is at a schema version older than this code applies."""

    def __init__(self, path: Path, version: int, expected: int) -> None:
        """Name the versions the runner would move between."""
        super().__init__(
            f"{path} is at schema version {version}; migrate the profile to "
            f"reach {expected}"
        )


class UnsupportedStoreVersionError(BronzeStorageError):
    """The store is at a schema version this code does not know."""

    def __init__(self, path: Path, version: int, expected: int) -> None:
        """Name the version found and the latest this code knows."""
        super().__init__(
            f"{path} is at schema version {version}, but this code knows {expected}"
        )


class MigrationResourceError(BronzeStorageError):
    """The packaged migration files are not a contiguous numbered set."""

    def __init__(self, detail: str) -> None:
        """Name what is wrong with the packaged resources."""
        super().__init__(f"the packaged Bronze migrations are unusable: {detail}")

    @classmethod
    def unmet_naming_rule(cls, name: str) -> "MigrationResourceError":
        """Name a file that does not start with its version."""
        return cls(f"{name} has no version prefix")

    @classmethod
    def not_contiguous(
        cls,
        expected: list[int],
        found: list[int],
    ) -> "MigrationResourceError":
        """Name the versions the runner expected and what it found."""
        return cls(f"expected versions {expected}, found {found}")

    @classmethod
    def empty(cls) -> "MigrationResourceError":
        """Report a package that carries no migrations at all."""
        return cls("no migrations were found")

    @classmethod
    def incomplete_statement(cls) -> "MigrationResourceError":
        """Report a file whose last statement never completes."""
        return cls("a migration ends with an incomplete statement")


class ForeignKeyViolationError(BronzeStorageError):
    """A migration would commit rows that break a foreign key."""

    def __init__(self, version: int, rows: int) -> None:
        """Name the migration and how many rows failed the check."""
        super().__init__(
            f"migration {version} would commit {rows} foreign-key violations"
        )


@dataclass(frozen=True)
class MigrationStep:
    """One numbered SQL migration, read from the packaged resources."""

    version: int
    sql: str


def migration_steps(directory: Path | None = None) -> tuple[MigrationStep, ...]:
    """Return the packaged Bronze migrations, oldest first."""
    raise NotImplementedError


def migrate_bronze(profile: Profile) -> None:
    """Create or upgrade the Bronze store that one profile names."""
    raise NotImplementedError


def open_bronze_connection(profile: Profile) -> sqlite3.Connection:
    """Open an existing Bronze store, refusing anything it cannot vouch for."""
    raise NotImplementedError
