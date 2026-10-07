# Copyright 2026 Therkel
"""Backup sets: a complete, checked copy of a profile, written whole or not at all.

A set is a folder under the profile's backups folder, named by its UTC time.
It holds a snapshot of each store taken through SQLite's backup API, a copy of
the inputs folder, and `manifest.json`, which is written last.

A set is written in the profile's local `backup-staging` folder first, beside
the live stores, and is published only once it is whole: it is copied into
the backups folder under a temporary name and renamed into place. A set is
complete when its manifest can be read and every file it lists has the
checksum it records; nothing else is ever used as a backup.
"""

import json
import os
import shutil
import sqlite3
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from importlib import metadata
from pathlib import Path
from typing import Final

from budget.bronze import BronzeStore
from budget.bronze.storage import bronze_stage
from budget.durability import sync_folder
from budget.importing import check_import_log
from budget.locking import WriterLock
from budget.profiles import (
    BRONZE_STORE_NAME,
    DECISION_LOG_FILE_NAME,
    IMPORT_LOG_FILE_NAME,
    INPUTS_FOLDER,
    SILVER_STORE_NAME,
    WRITER_LOCK_NAME,
    Profile,
    RetentionPolicy,
)
from budget.silver.storage import silver_stage
from budget.sqlstore import StageStore, is_started, open_store_for_backup

MANIFEST_FORMAT: Final = 1
RECOVERY_FORMAT: Final = 1
MANIFEST_NAME: Final = "manifest.json"
# A set's folder name: its UTC time, to the microsecond, with `-` for `:`,
# which Windows does not allow in a name.
SET_NAME_FORMAT: Final = "%Y-%m-%dT%H-%M-%S.%fZ"
# The suffix of a set being copied into the backups folder.
PUBLISHING_SUFFIX: Final = ".partial"
# The installed `budget` package, whose sources the code version fingerprints.
_PACKAGE: Final = Path(__file__).resolve().parent
_SOURCE_SUFFIXES: Final = frozenset({".py", ".sql"})
_IMPORT_LOG_IN_SET: Final = f"{INPUTS_FOLDER}/{IMPORT_LOG_FILE_NAME}"
# What Gold keeps in the stores folder (operations.md, Stores), which no set
# covers until Gold has a store.
_UNCOVERED_STAGE_STORES: Final = frozenset({"gold.db", "gold"})
# The stores a set covers, with the files SQLite keeps beside each, and the
# writer lock.
_COVERED_FILES: Final = frozenset(
    {
        WRITER_LOCK_NAME,
        *(
            f"{store}{suffix}"
            for store in (BRONZE_STORE_NAME, SILVER_STORE_NAME)
            for suffix in ("", "-wal", "-shm", "-journal")
        ),
    }
)
# The first bytes of every SQLite database file.
_SQLITE_HEADER: Final = b"SQLite format 3\x00"


class BackupWriteError(RuntimeError):
    """A backup set could not be written: nothing was published.

    What was staged is removed, so the backups folder is as it was.
    """

    def __init__(self, reason: str) -> None:
        """Say why, and that no set came of it."""
        super().__init__(
            f"the backup set could not be written: {reason}; nothing was published"
        )

    @classmethod
    def from_os_error(cls, error: OSError) -> "BackupWriteError":
        """Report the operating system's reason, without its path."""
        return cls(error.strerror or type(error).__name__)

    @classmethod
    def name_taken(cls, name: str) -> "BackupWriteError":
        """Report a set name another set already has."""
        return cls(f"a set named {name} already exists, and is never replaced")

    @classmethod
    def unreadable(cls, path: Path) -> "BackupWriteError":
        """Report a file that stands in the way, but cannot be read."""
        return cls(f"{path} cannot be read")


class BackupVerificationError(RuntimeError):
    """A backup set does not match its own manifest: nothing was published."""

    def __init__(self) -> None:
        """Say what failed, and that no set came of it."""
        super().__init__(
            "the backup set's copy does not match the checksums in its manifest; "
            "nothing was published"
        )


class UnsupportedStoresError(RuntimeError):
    """The stores folder holds a store this backup does not cover.

    Only the Bronze and Silver stores are backed up so far. A set that left
    another store out would claim to be a complete copy of the profile, so
    none is written.
    """

    def __init__(self, names: list[str]) -> None:
        """Name what was found in the stores folder."""
        super().__init__(
            f"the stores folder holds {', '.join(names)}, which no backup set "
            "covers yet: only the Bronze and Silver stores are backed up; "
            "nothing was published"
        )


class LostStoreError(RuntimeError):
    """A store the profile's backup sets hold is missing from the stores folder.

    A set without it would claim to be a complete copy of a profile that has
    lost a store, and retention would in time prune every set holding it.
    """

    def __init__(self, label: str) -> None:
        """Name the lost store, and what to do instead."""
        super().__init__(
            f"the stores folder has no {label} store, but backup sets of this "
            f"profile hold one: the {label} store must be restored from the "
            "newest that holds one; nothing was published"
        )


@dataclass(frozen=True)
class BackupSet:
    """One complete backup set: its folder name, its folder, and its time."""

    name: str
    path: Path
    created_at: datetime


def _set_name(now: datetime) -> str:
    """Name a set by its time in UTC."""
    return now.astimezone(UTC).strftime(SET_NAME_FORMAT)


def _set_time(name: str) -> datetime | None:
    """Return the time a set's folder name records, or `None` for another name."""
    try:
        return datetime.strptime(name, SET_NAME_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def _checksum(content: bytes) -> dict[str, object]:
    """Describe one file as the manifest records it: SHA-256 and length."""
    return {"sha256": sha256(content).hexdigest(), "bytes": len(content)}


def code_version() -> dict[str, str]:
    """Name the running code: its package version and a source fingerprint.

    The fingerprint is the SHA-256 of one line per `.py` and `.sql` file in
    the package, sorted: its `/`-separated path, a tab, its SHA-256, and a
    line feed. Any checkout can be compared with it, with or without git.
    """
    lines = sorted(
        f"{path.relative_to(_PACKAGE).as_posix()}\t"
        f"{sha256(path.read_bytes()).hexdigest()}\n"
        for path in _PACKAGE.rglob("*")
        if path.suffix in _SOURCE_SUFFIXES
    )
    return {
        "package": metadata.version(_PACKAGE.name),
        "source_sha256": sha256("".join(lines).encode("utf-8")).hexdigest(),
    }


def _write_synced(path: Path, content: bytes) -> None:
    """Write a file and force it to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())


def _snapshot(store: StageStore, target: Path) -> int:
    """Copy one stage's store to `target` through SQLite's backup API.

    The backup API reads the store as one consistent transaction, WAL
    included, which no copy of the store's files can promise. Returns the
    store's schema version.

    SQLite reports a copy it cannot write, such as on a full disk, as its own
    error rather than an `OSError`: that is a set that cannot be written too.
    """
    with closing(open_store_for_backup(store)) as source:
        try:
            with closing(sqlite3.connect(target)) as snapshot:
                source.backup(snapshot)
        except sqlite3.OperationalError as error:
            raise BackupWriteError(str(error)) from None
        return int(source.execute("PRAGMA user_version").fetchone()[0])


@dataclass(frozen=True)
class _StagedSet:
    """A set written in staging: what each file is, and its manifest's bytes.

    `files` maps each file's path in the set, with `/` separators, to what
    the manifest records about it. `schema_versions` maps each stage whose
    store the set holds to the schema version its snapshot was taken at.
    """

    files: dict[str, dict[str, object]]
    manifest: bytes
    schema_versions: dict[str, int]


def _covered_stores(profile: Profile) -> tuple[StageStore, ...]:
    """Name the stores a set of this profile holds: Bronze, and Silver's if any.

    Bronze's is always snapshotted, so a profile without one is refused. A
    Silver store is snapshotted where it is started; a profile that has none
    yet, or only a file an interrupted start left empty, is still copied whole
    without it.
    """
    silver = silver_stage(profile)
    return (bronze_stage(profile), *((silver,) if is_started(silver) else ()))


def _copy_inputs(profile: Profile, staging: Path) -> dict[str, bytes]:
    """Copy every file in the inputs folder into the set's `inputs` folder.

    Returns each copy's bytes by its path in the set, with `/` separators.
    """
    if not profile.inputs.is_dir():
        return {}
    copies = {}
    for found in sorted(profile.inputs.rglob("*")):
        relative = found.relative_to(profile.inputs).as_posix()
        source = profile.input_file(relative)
        if not source.is_file():
            continue
        content = source.read_bytes()
        in_set = f"{INPUTS_FOLDER}/{relative}"
        _write_synced(staging / in_set, content)
        copies[in_set] = content
    return copies


def _log_length(content: bytes | None) -> int:
    """Return how many bytes of a log are complete lines.

    A final line without its line feed was cut off by a crash: it is not an
    entry yet, so it is not counted.
    """
    return 0 if content is None else content.rfind(b"\n") + 1


def _stage(profile: Profile, staging: Path, now: datetime) -> _StagedSet:
    """Write a set's files into `staging`, and describe them."""
    staging.mkdir(parents=True)
    stores = _covered_stores(profile)
    schema_versions = {
        store.stage: _snapshot(store, staging / store.path.name) for store in stores
    }
    inputs = _copy_inputs(profile, staging)
    # The set must restore as it was taken: every logged run in the snapshot.
    with BronzeStore(profile, snapshot=staging / BRONZE_STORE_NAME) as snapshot:
        check_import_log(snapshot, inputs.get(_IMPORT_LOG_IN_SET, b""))
    files = {
        store.path.name: _checksum((staging / store.path.name).read_bytes())
        for store in stores
    }
    files.update({in_set: _checksum(content) for in_set, content in inputs.items()})
    manifest = {
        "format": MANIFEST_FORMAT,
        "profile": profile.name,
        "created_at": now.astimezone(UTC).isoformat(),
        "code_version": code_version(),
        "stores": {
            store.stage: {
                "path": store.path.name,
                "schema_version": schema_versions[store.stage],
            }
            for store in stores
        },
        "logs": {
            log: _log_length(inputs.get(f"{INPUTS_FOLDER}/{log}"))
            for log in (IMPORT_LOG_FILE_NAME, DECISION_LOG_FILE_NAME)
        },
        "files": files,
    }
    return _StagedSet(
        files=files,
        manifest=(json.dumps(manifest, indent=2) + "\n").encode("utf-8"),
        schema_versions=schema_versions,
    )


def _publish(profile: Profile, staging: Path, name: str, staged: _StagedSet) -> Path:
    """Copy a staged set into the backups folder, manifest last, then name it.

    The copy is made under a temporary name, so the backups folder never
    holds a set under its own name before every file is in it.
    """
    publishing = profile.backup_path(name + PUBLISHING_SUFFIX)
    target = profile.backup_path(name)
    if target.exists():
        raise BackupWriteError.name_taken(name)
    for relative in staged.files:
        _write_synced(publishing / relative, (staging / relative).read_bytes())
    _write_synced(publishing / MANIFEST_NAME, staged.manifest)
    sync_folder(publishing)
    if not _is_complete(publishing):
        raise BackupVerificationError
    publishing.rename(target)
    sync_folder(target.parent)
    return target


def _is_sqlite_database(path: Path) -> bool:
    """Report whether a file begins as every SQLite database does."""
    with path.open("rb") as file:
        return file.read(len(_SQLITE_HEADER)) == _SQLITE_HEADER


def _is_another_store(entry: Path) -> bool:
    """Report whether a stores-folder entry is a store no set covers."""
    if entry.name in _UNCOVERED_STAGE_STORES:
        return True
    # The lock is never read: on Windows, its locked byte refuses a reader.
    if entry.name in _COVERED_FILES or not entry.is_file():
        return False
    return _is_sqlite_database(entry)


def require_supported_stores(profile: Profile) -> None:
    """Refuse a stores folder holding any store besides Bronze and Silver.

    Gold's store, its legacy publications, and any other SQLite database are
    refused, even an empty file being created as one. The covered stores' own
    WAL and shared-memory files, the lock and folders such as `logs` are not
    stores.
    """
    if not profile.stores.is_dir():
        return
    found = [
        entry.name
        for entry in sorted(profile.stores.iterdir())
        if _is_another_store(entry)
    ]
    if found:
        raise UnsupportedStoresError(found)


def _require_no_lost_store(profile: Profile) -> None:
    """Refuse a backup while a store the profile's sets hold is missing.

    Only Silver's store may be missing from a set; Bronze's is always
    snapshotted. A file an interrupted start left empty is missing too, as it
    is to `_covered_stores`. Only a complete set counts, as for a new store
    (`migrate`): a damaged one restores nothing.
    """
    silver = silver_stage(profile)
    if not is_started(silver) and complete_set_holds(profile, silver.stage):
        raise LostStoreError(silver.label)


def _remove_interrupted(profile: Profile) -> None:
    """Delete what an interrupted backup left: never a set, only its parts.

    Everything in the staging folder is an unfinished set. In the backups
    folder, only a set's temporary publishing name is; a folder under a set's
    own name is left alone even without a manifest, because it is never
    selected and may be one a person is putting back by hand.
    """
    staging = profile.backup_staging
    if staging.is_dir():
        for leftover in staging.iterdir():
            shutil.rmtree(leftover, ignore_errors=True)
    backups = profile.backup_path(".")
    if backups.is_dir():
        for child in backups.iterdir():
            stem = child.name.removesuffix(PUBLISHING_SUFFIX)
            if stem != child.name and _set_time(stem) is not None:
                shutil.rmtree(profile.backup_path(child.name), ignore_errors=True)


def back_up(lock: WriterLock, *, now: datetime) -> BackupSet:
    """Write one complete backup set under the held writer lock.

    `now` names the set; the caller reads the clock, so this never does.
    """
    profile = lock.profile
    name = _set_name(now)
    staging = profile.backup_staging / name
    publishing = profile.backup_path(name + PUBLISHING_SUFFIX)
    try:
        require_supported_stores(profile)
        _require_no_lost_store(profile)
        _remove_interrupted(profile)
        staged = _stage(profile, staging, now)
        path = _publish(profile, staging, name, staged)
    except OSError as error:
        raise BackupWriteError.from_os_error(error) from None
    finally:
        # Whatever happened, nothing staged or half-published is kept.
        shutil.rmtree(staging, ignore_errors=True)
        if publishing.is_dir():
            shutil.rmtree(publishing, ignore_errors=True)
    # The set is published: retention and release that fail now only leave
    # sets held or kept until the next backup, so neither fails this one.
    with suppress(OSError):
        _release_superseded(profile, staged.schema_versions)
    with suppress(OSError):
        _prune(profile, name, now)
    return BackupSet(name=name, path=path, created_at=now)


def _read_manifest(folder: Path) -> dict[str, object] | None:
    """Return a set's manifest, or `None` when it is missing or unreadable."""
    try:
        document = json.loads((folder / MANIFEST_NAME).read_bytes())
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    manifest: dict[str, object] = {str(key): value for key, value in document.items()}
    return manifest


def _matches(folder: Path, relative: object, recorded: object) -> bool:
    """Report whether one file in a set is what its manifest records."""
    if not isinstance(relative, str):
        return False
    try:
        content = (folder / relative).read_bytes()
    except OSError:
        return False
    return _checksum(content) == recorded


def _is_complete(folder: Path) -> bool:
    """Report whether a set's manifest reads and every file matches it."""
    manifest = _read_manifest(folder)
    if manifest is None or manifest.get("format") != MANIFEST_FORMAT:
        return False
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        return False
    return all(
        _matches(folder, relative, recorded) for relative, recorded in files.items()
    )


def complete_backup_sets(profile: Profile) -> tuple[BackupSet, ...]:
    """Return the profile's complete backup sets, newest first.

    A folder whose name is not a set's time, a set without a manifest, and a
    set whose files do not match their checksums are left out.
    """
    folder = profile.backup_path(".")
    if not folder.is_dir():
        return ()
    found = []
    for child in folder.iterdir():
        created_at = _set_time(child.name)
        if created_at is not None and child.is_dir() and _is_complete(child):
            found.append(BackupSet(name=child.name, path=child, created_at=created_at))
    return tuple(
        sorted(found, key=lambda found_set: found_set.created_at, reverse=True)
    )


def _lists_store(manifest: dict[str, object], stage: str) -> bool:
    """Report whether a manifest lists a store for `stage`.

    A listed store counts whatever else its entry records.
    """
    stores = manifest.get("stores")
    return isinstance(stores, dict) and stage in stores


def complete_set_holds(profile: Profile, stage: str) -> bool:
    """Report whether any complete backup set of the profile holds `stage`'s store.

    Manifests are read first, so a set's files are checked only when it
    lists that store: sets of Bronze alone are never read through.
    """
    backups = profile.backup_path(".")
    if not backups.is_dir():
        return False
    for child in backups.iterdir():
        if _set_time(child.name) is None:
            continue
        manifest = _read_manifest(child)
        if (
            manifest is not None
            and _lists_store(manifest, stage)
            and _is_complete(child)
        ):
            return True
    return False


def _prunable_sets(profile: Profile) -> dict[str, datetime]:
    """Return each set retention may delete, by name, with its time.

    Only a set whose manifest this code can read is one: a set written by a
    later version may record a reason to keep it that this code cannot see.
    Its files are not checked again here, which would read every set.
    """
    backups = profile.backup_path(".")
    found = {}
    for child in backups.iterdir():
        created_at = _set_time(child.name)
        if created_at is None:
            continue
        manifest = _read_manifest(child)
        if manifest is not None and manifest.get("format") == MANIFEST_FORMAT:
            found[child.name] = created_at
    return found


def _months_between(earlier: datetime, later: datetime) -> int:
    """Count calendar months from `earlier`'s month to `later`'s."""
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def _kept_by_policy(
    sets: dict[str, datetime], policy: RetentionPolicy, now: datetime
) -> set[str]:
    """Name the sets the retention policy keeps at `now`.

    Every set from the last `keep_all_days` days; then the newest set of each
    day for `keep_daily_days` days; then the newest set of each month, for
    `keep_monthly` months counting this one, or forever. Days and months are
    UTC, as set names are.
    """
    newest_of_day: dict[object, str] = {}
    newest_of_month: dict[object, str] = {}
    for name, created_at in sorted(sets.items(), key=lambda item: item[1]):
        newest_of_day[created_at.date()] = name
        newest_of_month[created_at.year, created_at.month] = name
    kept = set()
    for name, created_at in sets.items():
        age = now - created_at
        months = _months_between(created_at, now)
        if (
            age < timedelta(days=policy.keep_all_days)
            or (
                age < timedelta(days=policy.keep_daily_days)
                and newest_of_day[created_at.date()] == name
            )
            or (
                newest_of_month[created_at.year, created_at.month] == name
                and (policy.keep_monthly is None or months < policy.keep_monthly)
            )
        ):
            kept.add(name)
    return kept


def _delete_set(profile: Profile, name: str) -> None:
    """Delete one set, first taking it out from under its name.

    Renamed as a set being published, it is never selected again, and the
    next backup finishes deleting it if this cannot. A failure to delete is
    left for that backup: an old set kept a little longer is harmless.
    """
    deleting = profile.backup_path(name + PUBLISHING_SUFFIX)
    try:
        profile.backup_path(name).rename(deleting)
    except OSError:
        return
    shutil.rmtree(deleting, ignore_errors=True)


def _prune(profile: Profile, newest: str, now: datetime) -> None:
    """Delete the sets the profile's retention policy no longer keeps.

    The set just written is always kept, whatever the policy says, and so is
    every set an unfinished operation holds. When the file naming those
    cannot be read, nothing is deleted.
    """
    held = _held_for_recovery(profile)
    if held is None:
        return
    sets = _prunable_sets(profile)
    kept = _kept_by_policy(sets, profile.retention, now) | {newest} | held
    for name in sorted(set(sets) - kept):
        _delete_set(profile, name)


def _held_for_recovery(profile: Profile) -> set[str] | None:
    """Name the sets an unfinished operation holds, or `None` if unreadable.

    No file means none is held.
    """
    try:
        document = json.loads(profile.recovery_sets_file.read_bytes())
    except FileNotFoundError:
        return set()
    except (OSError, ValueError):
        return None
    held = document.get("sets") if isinstance(document, dict) else None
    if not isinstance(held, list) or not all(isinstance(name, str) for name in held):
        return None
    return {str(name) for name in held}


def _write_held(profile: Profile, held: set[str]) -> None:
    """Replace `recovery-sets.json` with `held`, or remove it when empty."""
    path = profile.recovery_sets_file
    if not held:
        path.unlink(missing_ok=True)
        return
    document = {"format": RECOVERY_FORMAT, "sets": sorted(held)}
    content = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    partial = path.with_name(path.name + PUBLISHING_SUFFIX)
    partial.unlink(missing_ok=True)
    _write_synced(partial, content)
    partial.replace(path)
    sync_folder(path.parent)


def hold_for_recovery(lock: WriterLock, backup: BackupSet) -> None:
    """Keep a set from retention until the operation it protects finishes.

    A migration holds the set it took first; if it fails or is cut off, that
    set stays until `release_recovery_sets` is called after one succeeds.

    An existing `recovery-sets.json` that cannot be read or parsed may be
    hiding a set another unfinished operation still needs: it is refused
    rather than overwritten, and the migration this guards stops before
    touching the schema (decision 7). A write that fails partway is reported
    the same way, instead of escaping as an unhandled `OSError`.
    """
    profile = lock.profile
    held = _held_for_recovery(profile)
    if held is None:
        raise BackupWriteError.unreadable(profile.recovery_sets_file)
    try:
        _write_held(profile, held | {backup.name})
    except OSError as error:
        raise BackupWriteError.from_os_error(error) from None


def release_recovery_sets(lock: WriterLock) -> None:
    """Let retention treat every held set like any other again."""
    lock.profile.recovery_sets_file.unlink(missing_ok=True)


def _set_schema_version(manifest: dict[str, object], stage: str) -> int | None:
    """Return a set's recorded schema version for one stage, or `None`."""
    stores = manifest.get("stores")
    if not isinstance(stores, dict):
        return None
    store = stores.get(stage)
    if not isinstance(store, dict):
        return None
    version = store.get("schema_version")
    return version if isinstance(version, int) else None


def _superseded(profile: Profile, name: str, schema_versions: dict[str, int]) -> bool:
    """Report whether any store a held set records is behind the fresh set's."""
    manifest = _read_manifest(profile.backup_path(name))
    if manifest is None:
        return False
    for stage, schema_version in schema_versions.items():
        found = _set_schema_version(manifest, stage)
        if found is not None and found < schema_version:
            return True
    return False


def _release_superseded(profile: Profile, schema_versions: dict[str, int]) -> None:
    """Drop a held set once a fresh set shows the schema has moved past it.

    A held set still at every live schema version is a failed or interrupted
    migration's only recovery set, and stays held regardless of how many
    backups are written in the meantime; only a set with a store whose own
    schema version is behind the fresh set's is released, since the
    migration it was taken for has then committed. A store the held set does
    not record, such as Silver in a set written before backups covered it,
    is not compared. While the held sets cannot be read, nothing changes
    here either.
    """
    held = _held_for_recovery(profile)
    if not held:
        return
    kept = {name for name in held if not _superseded(profile, name, schema_versions)}
    if kept != held:
        _write_held(profile, kept)
