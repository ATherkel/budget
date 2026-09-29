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
_MIGRATIONS_FOLDER: Final = (
    Path(__file__).resolve().parent.parent / "migrations" / "bronze"
)


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
    folder = _MIGRATIONS_FOLDER if directory is None else Path(directory)
    steps = []
    for path in sorted(folder.glob("*.sql")):
        try:
            version = int(path.name.split("_", 1)[0])
        except ValueError:
            raise MigrationResourceError.unmet_naming_rule(path.name) from None
        steps.append(MigrationStep(version=version, sql=path.read_text("utf-8")))
    expected = list(range(1, len(steps) + 1))
    if [step.version for step in steps] != expected:
        found = [step.version for step in steps]
        raise MigrationResourceError.not_contiguous(expected, found)
    if not steps:
        raise MigrationResourceError.empty()
    return tuple(steps)


def _require_supported_sqlite() -> None:
    """Refuse this interpreter before any file is touched."""
    if sqlite3.sqlite_version_info < SQLITE_VERSION_FLOOR:
        raise UnsupportedSQLiteVersionError(sqlite3.sqlite_version_info)


def _connect(path: Path, *, mode: str) -> sqlite3.Connection:
    """Connect through a URI, so a path's spaces and symbols stay literal."""
    connection = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _apply_connection_settings(connection: sqlite3.Connection) -> None:
    """Set the per-connection pragmas ADR-013 requires."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA synchronous = FULL")


def _read_version(connection: sqlite3.Connection) -> int:
    """Return the store's schema version."""
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def _has_objects(connection: sqlite3.Connection) -> bool:
    """Report whether the file holds any table, view, index or trigger."""
    row = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type IN ('table', 'view', 'index', 'trigger')
            AND name NOT LIKE 'sqlite_%'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _require_identity(
    connection: sqlite3.Connection,
    path: Path,
    profile: Profile,
) -> None:
    """Refuse a store that belongs to another profile or stage."""
    try:
        rows = connection.execute(
            "SELECT profile, stage FROM store_identity"
        ).fetchall()
    except sqlite3.OperationalError:
        raise StoreIdentityError(path, "it has no store_identity table") from None
    if len(rows) != 1:
        raise StoreIdentityError(path, "its store_identity is not one row")
    found_profile = rows[0]["profile"]
    found_stage = rows[0]["stage"]
    if found_profile != profile.name or found_stage != BRONZE_STAGE:
        raise StoreIdentityError(
            path,
            f"it belongs to profile {found_profile!r} stage {found_stage!r}",
        )


def _statements(sql: str) -> list[str]:
    """Split one migration file into complete statements.

    `executescript` commits whatever transaction is open, so the runner sends
    each statement through `execute` instead. Comments and blank lines stay
    attached to the statement that follows them.
    """
    statements = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer)
            buffer = ""
    if buffer.strip():
        raise MigrationResourceError.incomplete_statement()
    return statements


def _require_no_foreign_key_violations(
    connection: sqlite3.Connection,
    version: int,
) -> None:
    """Fail a migration that would commit rows breaking a foreign key."""
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise ForeignKeyViolationError(version, len(violations))


def _apply_step(
    connection: sqlite3.Connection,
    profile: Profile,
    step: MigrationStep,
) -> None:
    """Apply one migration and its version bump in one transaction."""
    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in _statements(step.sql):
            connection.execute(statement)
        if step.version == 1:
            connection.execute(
                "INSERT INTO store_identity (profile, stage) VALUES (?, ?)",
                (profile.name, BRONZE_STAGE),
            )
        _require_no_foreign_key_violations(connection, step.version)
        connection.execute(f"PRAGMA user_version = {step.version}")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def migrate_bronze(profile: Profile) -> None:
    """Create or upgrade the Bronze store that one profile names.

    The production profile is refused before any folder or file is touched:
    production migration waits for the backup and command work.
    """
    _require_supported_sqlite()
    if profile.name == PRODUCTION_PROFILE_NAME:
        raise ProductionMigrationBlockedError

    steps = migration_steps()
    latest = steps[-1].version
    path = profile.bronze_store
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path, mode="rwc")
    try:
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA synchronous = FULL")
        version = _read_version(connection)
        if not _has_objects(connection):
            connection.execute("PRAGMA journal_mode = WAL")
        elif version == 0:
            raise UnversionedStoreError(path)
        elif version > latest:
            raise UnsupportedStoreVersionError(path, version, latest)
        if version >= 1:
            _require_identity(connection, path, profile)

        pending = [step for step in steps if step.version > version]
        if pending:
            # The pragma cannot change inside a transaction, and a table
            # rebuild must be free to drop rows before the check below.
            connection.execute("PRAGMA foreign_keys = OFF")
            try:
                for step in pending:
                    _apply_step(connection, profile, step)
            finally:
                connection.execute("PRAGMA foreign_keys = ON")
    finally:
        connection.close()


def _require_current_version(connection: sqlite3.Connection, path: Path) -> None:
    """Refuse a store this code cannot open at its own version."""
    version = _read_version(connection)
    latest = migration_steps()[-1].version
    if version < latest:
        raise MigrationRequiredError(path, version, latest)
    if version > latest:
        raise UnsupportedStoreVersionError(path, version, latest)


def open_bronze_connection(profile: Profile) -> sqlite3.Connection:
    """Open an existing Bronze store, refusing anything it cannot vouch for."""
    _require_supported_sqlite()
    path = profile.bronze_store
    if not path.exists():
        raise StoreNotFoundError(path)

    connection = _connect(path, mode="rw")
    try:
        _apply_connection_settings(connection)
        _require_current_version(connection, path)
        _require_identity(connection, path, profile)
    except BaseException:
        connection.close()
        raise
    return connection
