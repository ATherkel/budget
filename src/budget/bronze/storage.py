# Copyright 2026 Therkel
"""Creating, upgrading and opening the Bronze store file.

Only `migrate_bronze` creates or changes the schema. Opening a store never
does: it refuses a file that is missing, belongs to another profile or stage,
or is at a schema version this code does not know. The numbered SQL lives in
`budget/migrations/bronze/` inside the installed package, next to the runner
that applies it, and each stage keeps its own `PRAGMA user_version`.
"""

import sqlite3
from collections.abc import Callable
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
    """Production is migrated only by `budget migrate`, which backs up first."""

    def __init__(self) -> None:
        """State the one way production is migrated, without naming any path."""
        super().__init__(
            "the production profile is migrated only by `budget migrate`, "
            "which writes a backup set first"
        )


class NewStoreRequiredError(BronzeStorageError):
    """Production has no Bronze store, and a new one was not asked for.

    A missing production store may be a lost one, which a backup set must
    restore; starting an empty store in its place is a deliberate act.
    """

    def __init__(self) -> None:
        """Say how to start one, and when not to."""
        super().__init__(
            "the production profile has no Bronze store: start one with "
            "`budget migrate --new-store`, unless production had one, which must "
            "be restored from a backup set instead"
        )


class NewStoreRefusedError(BronzeStorageError):
    """A new production store was asked for where one already exists."""

    def __init__(self, path: Path) -> None:
        """Name the store that already exists."""
        super().__init__(
            f"{path} is already a Bronze store: migrate it without --new-store"
        )


class StoreNotFoundError(BronzeStorageError):
    """No store file exists at the profile's path."""

    def __init__(self, path: Path) -> None:
        """Name the path that has no store."""
        super().__init__(f"no Bronze store at {path}: migrate the profile first")


class StoreBusyError(BronzeStorageError):
    """Another program held the store past the busy timeout."""

    def __init__(self, path: Path) -> None:
        """Name the store and what the operator can do about it."""
        super().__init__(f"{path} is in use by another program: close it and rerun")


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
class _MigrationStep:
    """One numbered SQL migration, read from the packaged resources."""

    version: int
    sql: str


def _migration_steps() -> tuple[_MigrationStep, ...]:
    """Return the packaged Bronze migrations, oldest first."""
    steps = []
    for path in sorted(_MIGRATIONS_FOLDER.glob("*.sql")):
        try:
            version = int(path.name.split("_", 1)[0])
        except ValueError:
            raise MigrationResourceError.unmet_naming_rule(path.name) from None
        steps.append(_MigrationStep(version=version, sql=path.read_text("utf-8")))
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


def _is_only_comments(text: str) -> bool:
    """Report whether text holds nothing but SQL comments and whitespace."""
    remaining = text
    while remaining.strip():
        stripped = remaining.lstrip()
        if stripped.startswith("--"):
            newline = stripped.find(chr(10))
            if newline == -1:
                return True
            remaining = stripped[newline + 1 :]
            continue
        if stripped.startswith("/*"):
            end = stripped.find("*/")
            if end == -1:
                return False
            remaining = stripped[end + 2 :]
            continue
        return False
    return True


def _statements(sql: str) -> list[str]:
    """Split one migration file into complete statements.

    The runner sends each statement through execute, because executescript
    commits whatever transaction is open. Statements end where SQLite itself
    reports one complete, so semicolons inside strings and triggers stay in
    their statement and several statements may share a line; comments stay
    attached to the statement that follows, and a trailing comment after the
    last statement is not a statement at all.
    """
    statements = []
    start = 0
    for index, character in enumerate(sql):
        if character != ";":
            continue
        candidate = sql[start : index + 1]
        if sqlite3.complete_statement(candidate):
            statements.append(candidate)
            start = index + 1
    remainder = sql[start:]
    if remainder.strip() and not _is_only_comments(remainder):
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
    step: _MigrationStep,
) -> None:
    """Apply one migration and its version bump in the open transaction."""
    for statement in _statements(step.sql):
        connection.execute(statement)
    if step.version == 1:
        connection.execute(
            "INSERT INTO store_identity (singleton, profile, stage) VALUES (1, ?, ?)",
            (profile.name, BRONZE_STAGE),
        )
    _require_no_foreign_key_violations(connection, step.version)
    connection.execute(f"PRAGMA user_version = {step.version}")


def require_migration_allowed(profile: Profile, *, new_store: bool = False) -> None:
    """Refuse a migration this interpreter or profile cannot run.

    These checks touch no folder or file, so a command can run them before it
    takes the profile's writer lock. A production profile without a Bronze
    store is refused unless a new store is asked for: a missing store may be
    a lost one, which a backup set must restore instead.
    """
    _require_supported_sqlite()
    if (
        profile.name == PRODUCTION_PROFILE_NAME
        and not new_store
        and not profile.bronze_store.exists()
    ):
        raise NewStoreRequiredError


def _require_migratable(
    connection: sqlite3.Connection,
    path: Path,
    profile: Profile,
    latest: int,
) -> bool:
    """Refuse a store no migration may touch; report whether it is new.

    Nothing is written: an unsupported or unversioned store must stay exactly
    as it was found. A new store is an empty file, or none.
    """
    version = _read_version(connection)
    has_objects = _has_objects(connection)
    if version < 0 or version > latest:
        raise UnsupportedStoreVersionError(path, version, latest)
    if version == 0 and has_objects:
        raise UnversionedStoreError(path)
    if version >= 1:
        _require_identity(connection, path, profile)
    return version == 0


def _require_production_store_choice(path: Path, *, new: bool, new_store: bool) -> None:
    """Start a production store only when asked, and only where none exists."""
    if new and not new_store:
        raise NewStoreRequiredError
    if new_store and not new:
        raise NewStoreRefusedError(path)


def _apply_steps(
    connection: sqlite3.Connection,
    profile: Profile,
    steps: list[_MigrationStep],
) -> None:
    """Apply every pending step in one transaction, with foreign keys off.

    A step that fails rolls back the steps before it too, so the store stays
    at the version it had: never at one between it and the code's.
    """
    # The pragma cannot change inside a transaction, and a table rebuild must
    # be free to drop rows before the foreign-key check.
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for step in steps:
            _apply_step(connection, profile, step)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


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
    production = profile.name == PRODUCTION_PROFILE_NAME
    if production and before_migrating is None:
        raise ProductionMigrationBlockedError
    require_migration_allowed(profile, new_store=new_store)

    steps = _migration_steps()
    latest = steps[-1].version
    path = profile.bronze_store
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path, mode="rwc")
    try:
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA synchronous = FULL")
        new = _require_migratable(connection, path, profile, latest)
        if production:
            _require_production_store_choice(path, new=new, new_store=new_store)
        if new:
            connection.execute("PRAGMA journal_mode = WAL")
        pending = [step for step in steps if step.version > _read_version(connection)]
        if not pending:
            return False
        if before_migrating is not None and not new:
            before_migrating()
        _apply_steps(connection, profile, pending)
    except sqlite3.OperationalError as error:
        # The primary code, so BUSY's extended variants count too; any other
        # operational error, such as a broken migration, stays a defect.
        if error.sqlite_errorcode & 0xFF != sqlite3.SQLITE_BUSY:
            raise
        raise StoreBusyError(path) from None
    finally:
        connection.close()
    return True


def _require_current_version(connection: sqlite3.Connection, path: Path) -> None:
    """Refuse a store this code cannot open at its own version."""
    version = _read_version(connection)
    latest = _migration_steps()[-1].version
    if version < latest:
        raise MigrationRequiredError(path, version, latest)
    if version > latest:
        raise UnsupportedStoreVersionError(path, version, latest)


def _require_known_version(connection: sqlite3.Connection, path: Path) -> None:
    """Refuse a store at no schema version, or one newer than this code."""
    version = _read_version(connection)
    latest = _migration_steps()[-1].version
    if not 1 <= version <= latest:
        raise UnsupportedStoreVersionError(path, version, latest)


def open_bronze_for_backup(profile: Profile) -> sqlite3.Connection:
    """Open the profile's live Bronze store to copy it into a backup set.

    Unlike `open_bronze_connection`, a store older than the code is opened:
    production backs a store up before migrating it. The caller only reads.
    """
    _require_supported_sqlite()
    path = profile.bronze_store
    if not path.exists():
        raise StoreNotFoundError(path)
    connection = _connect(path, mode="rw")
    try:
        _apply_connection_settings(connection)
        _require_known_version(connection, path)
        _require_identity(connection, path, profile)
    except BaseException:
        connection.close()
        raise
    return connection


def open_bronze_snapshot(profile: Profile, path: Path) -> sqlite3.Connection:
    """Open a backup snapshot of the profile's Bronze store, read-only.

    The snapshot is opened `immutable`, so reading it never writes a WAL or
    shared-memory file beside it. It must be this profile's Bronze store at a
    schema version this code knows; a snapshot taken before a migration may
    be older than the code.
    """
    _require_supported_sqlite()
    uri = f"{path.as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        _require_known_version(connection, path)
        _require_identity(connection, path, profile)
    except BaseException:
        connection.close()
        raise
    return connection


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
