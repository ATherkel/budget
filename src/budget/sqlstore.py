# Copyright 2026 Therkel
"""Creating, upgrading and opening one ETL stage's SQLite store.

Every stage store follows ADR-013 and ADR-015: numbered plain SQL files that
ship beside this runner inside the installed package, applied in order, every
pending file and its `PRAGMA user_version` bump in one transaction, and a one-row
`store_identity` table naming the profile and the stage that own the file.
Only an explicit `migrate` creates or changes a store. Opening a store never
does: it refuses a file that is missing, belongs to another profile or stage,
or is at a schema version this code does not know.

Each stage names itself and its own migration folder in a `StageStore`, so the
runner, the refusals and the connection settings stay in one place while the
files, the recorded stage and the messages stay stage-specific.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from budget.profiles import PRODUCTION_PROFILE_NAME, Profile

SQLITE_VERSION_FLOOR: Final = (3, 51, 3)
BUSY_TIMEOUT_MS: Final = 5000


class StoreError(RuntimeError):
    """A refusal that comes from a store's file or runtime, not its content."""


class UnsupportedSQLiteVersionError(StoreError):
    """The SQLite in this interpreter is below the store's version floor."""

    def __init__(self, version: tuple[int, ...]) -> None:
        """Name the measured version and the floor."""
        measured = ".".join(str(part) for part in version)
        floor = ".".join(str(part) for part in SQLITE_VERSION_FLOOR)
        super().__init__(f"SQLite {measured} is below the required {floor}")


class ProductionMigrationBlockedError(StoreError):
    """Production's backup sets cover no Silver store, so none is migrated."""

    def __init__(self) -> None:
        """Name what production's backup sets hold, and what is refused."""
        super().__init__(
            "the production profile's backup sets hold the Bronze store alone, "
            "so the production profile migrates no Silver store"
        )


class StoreNotFoundError(StoreError):
    """No store file exists at the profile's path."""

    def __init__(self, label: str, path: Path) -> None:
        """Name the stage that has no store and the path it would live at."""
        super().__init__(f"no {label} store at {path}: migrate the profile first")


class StoreBusyError(StoreError):
    """Another program held the store past the busy timeout."""

    def __init__(self, path: Path) -> None:
        """Name the store and what the operator can do about it."""
        super().__init__(f"{path} is in use by another program: close it and rerun")


class UnversionedStoreError(StoreError):
    """An existing store carries tables but no schema version."""

    def __init__(self, path: Path) -> None:
        """Keep the bytes and ask for a deliberate migration."""
        super().__init__(
            f"{path} is an existing store without a schema version; it is not "
            "adopted automatically. Keep the file and migrate it deliberately."
        )


class StoreIdentityError(StoreError):
    """The store's recorded profile or stage is not the one being opened."""

    def __init__(self, path: Path, detail: str) -> None:
        """Name the store and what did not match."""
        super().__init__(f"{path} cannot be opened: {detail}")


class MigrationRequiredError(StoreError):
    """The store is at a schema version older than this code applies."""

    def __init__(self, path: Path, version: int, expected: int) -> None:
        """Name the versions the runner would move between."""
        super().__init__(
            f"{path} is at schema version {version}; migrate the profile to "
            f"reach {expected}"
        )


class UnsupportedStoreVersionError(StoreError):
    """The store is at a schema version this code does not know."""

    def __init__(self, path: Path, version: int, expected: int) -> None:
        """Name the version found and the latest this code knows."""
        super().__init__(
            f"{path} is at schema version {version}, but this code knows {expected}"
        )


class MigrationResourceError(StoreError):
    """The packaged migration files are not a contiguous numbered set."""

    def __init__(self, label: str, detail: str) -> None:
        """Name the stage whose packaged resources are unusable."""
        super().__init__(f"the packaged {label} migrations are unusable: {detail}")


class ForeignKeyViolationError(StoreError):
    """A migration would commit rows that break a foreign key."""

    def __init__(self, version: int, rows: int) -> None:
        """Name the migration and how many rows failed the check."""
        super().__init__(
            f"migration {version} would commit {rows} foreign-key violations"
        )


@dataclass(frozen=True)
class StageStore:
    """One profile's store for one ETL stage: what it records and where it is.

    `stage` is the value the store records for itself and checks when it opens;
    `label` is the stage's name in a refusal or an error message; `path` is the
    store file the profile names; `migrations` is the packaged SQL folder.
    """

    profile: Profile
    stage: str
    label: str
    path: Path
    migrations: Path


@dataclass(frozen=True)
class _MigrationStep:
    """One numbered SQL migration, read from the packaged resources."""

    version: int
    sql: str


def _migration_steps(store: StageStore) -> tuple[_MigrationStep, ...]:
    """Return the packaged migrations for one stage, oldest first."""
    steps = []
    for path in sorted(store.migrations.glob("*.sql")):
        try:
            version = int(path.name.split("_", 1)[0])
        except ValueError:
            raise MigrationResourceError(
                store.label, f"{path.name} has no version prefix"
            ) from None
        steps.append(_MigrationStep(version=version, sql=path.read_text("utf-8")))
    expected = list(range(1, len(steps) + 1))
    if [step.version for step in steps] != expected:
        found = [step.version for step in steps]
        raise MigrationResourceError(
            store.label, f"expected versions {expected}, found {found}"
        )
    if not steps:
        raise MigrationResourceError(store.label, "no migrations were found")
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
    store: StageStore,
) -> None:
    """Refuse a store that belongs to another profile or stage."""
    path = store.path
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
    if found_profile != store.profile.name or found_stage != store.stage:
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


def _statements(sql: str, label: str) -> list[str]:
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
        raise MigrationResourceError(
            label, "a migration ends with an incomplete statement"
        )
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
    store: StageStore,
    step: _MigrationStep,
) -> None:
    """Apply one migration and its version bump in the open transaction."""
    for statement in _statements(step.sql, store.label):
        connection.execute(statement)
    if step.version == 1:
        connection.execute(
            "INSERT INTO store_identity (singleton, profile, stage) VALUES (1, ?, ?)",
            (store.profile.name, store.stage),
        )
    _require_no_foreign_key_violations(connection, step.version)
    connection.execute(f"PRAGMA user_version = {step.version}")


def _apply_steps(
    connection: sqlite3.Connection,
    store: StageStore,
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
            _apply_step(connection, store, step)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def require_migration_allowed(profile: Profile) -> None:
    """Refuse a migration this interpreter or profile cannot run.

    These checks touch no folder or file, so a command can run them before it
    takes the profile's writer lock. Production is refused: its backup sets
    hold the Bronze store alone, so a Silver store there is not migrated.
    """
    _require_supported_sqlite()
    if profile.name == PRODUCTION_PROFILE_NAME:
        raise ProductionMigrationBlockedError


def migrate_store(store: StageStore) -> None:
    """Create or upgrade one stage store, refusing anything it cannot vouch for.

    The production profile is refused before any folder or file is touched.
    """
    require_migration_allowed(store.profile)

    steps = _migration_steps(store)
    latest = steps[-1].version
    path = store.path
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path, mode="rwc")
    try:
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA synchronous = FULL")
        version = _read_version(connection)
        has_objects = _has_objects(connection)
        # Validate the store before any persistent write: a journal-mode change
        # is a write, and an unsupported or unversioned store must stay exactly
        # as it was found.
        if version < 0 or version > latest:
            raise UnsupportedStoreVersionError(path, version, latest)
        if version == 0 and has_objects:
            raise UnversionedStoreError(path)
        if version >= 1:
            _require_identity(connection, store)
        elif not has_objects:
            connection.execute("PRAGMA journal_mode = WAL")

        pending = [step for step in steps if step.version > version]
        if pending:
            _apply_steps(connection, store, pending)
    except sqlite3.OperationalError as error:
        # The primary code, so BUSY's extended variants count too; any other
        # operational error, such as a broken migration, stays a defect.
        if error.sqlite_errorcode & 0xFF != sqlite3.SQLITE_BUSY:
            raise
        raise StoreBusyError(path) from None
    finally:
        connection.close()


def _require_current_version(connection: sqlite3.Connection, store: StageStore) -> None:
    """Refuse a store this code cannot open at its own version."""
    version = _read_version(connection)
    latest = _migration_steps(store)[-1].version
    if version < latest:
        raise MigrationRequiredError(store.path, version, latest)
    if version > latest:
        raise UnsupportedStoreVersionError(store.path, version, latest)


def open_store_connection(store: StageStore) -> sqlite3.Connection:
    """Open an existing stage store, refusing anything it cannot vouch for."""
    _require_supported_sqlite()
    path = store.path
    if not path.exists():
        raise StoreNotFoundError(store.label, path)

    connection = _connect(path, mode="rw")
    try:
        _apply_connection_settings(connection)
        _require_current_version(connection, store)
        _require_identity(connection, store)
    except BaseException:
        connection.close()
        raise
    return connection
