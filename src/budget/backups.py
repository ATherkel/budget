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
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from importlib import metadata
from pathlib import Path
from typing import Final

from budget.bronze.storage import BRONZE_STAGE, open_bronze_connection
from budget.locking import WriterLock
from budget.profiles import (
    BRONZE_STORE_NAME,
    DECISION_LOG_FILE_NAME,
    IMPORT_LOG_FILE_NAME,
    INPUTS_FOLDER,
    Profile,
)

MANIFEST_FORMAT: Final = 1
MANIFEST_NAME: Final = "manifest.json"
# A set's folder name: its UTC time, to the microsecond, with `-` for `:`,
# which Windows does not allow in a name.
SET_NAME_FORMAT: Final = "%Y-%m-%dT%H-%M-%S.%fZ"
# The suffix of a set being copied into the backups folder.
PUBLISHING_SUFFIX: Final = ".partial"
# The installed `budget` package, whose sources the code version fingerprints.
_PACKAGE: Final = Path(__file__).resolve().parent
_SOURCE_SUFFIXES: Final = frozenset({".py", ".sql"})


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


def _sync_folder(folder: Path) -> None:
    """Force a folder's new entries to disk, where the platform allows it.

    Windows cannot open a folder to fsync it; NTFS journals a rename itself.
    """
    if sys.platform == "win32":
        return
    descriptor = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_synced(path: Path, content: bytes) -> None:
    """Write a file and force it to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())


def _snapshot_bronze(profile: Profile, target: Path) -> int:
    """Copy the Bronze store to `target` through SQLite's backup API.

    The backup API reads the store as one consistent transaction, WAL
    included, which no copy of the store's files can promise. Returns the
    store's schema version.
    """
    with (
        closing(open_bronze_connection(profile)) as source,
        closing(sqlite3.connect(target)) as snapshot,
    ):
        source.backup(snapshot)
        return int(source.execute("PRAGMA user_version").fetchone()[0])


@dataclass(frozen=True)
class _StagedSet:
    """A set written in staging: what each file is, and its manifest's bytes.

    `files` maps each file's path in the set, with `/` separators, to what
    the manifest records about it.
    """

    files: dict[str, dict[str, object]]
    manifest: bytes


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
    store = staging / BRONZE_STORE_NAME
    schema_version = _snapshot_bronze(profile, store)
    inputs = _copy_inputs(profile, staging)
    files = {BRONZE_STORE_NAME: _checksum(store.read_bytes())}
    files.update({in_set: _checksum(content) for in_set, content in inputs.items()})
    manifest = {
        "format": MANIFEST_FORMAT,
        "profile": profile.name,
        "created_at": now.astimezone(UTC).isoformat(),
        "code_version": code_version(),
        "stores": {
            BRONZE_STAGE: {"path": BRONZE_STORE_NAME, "schema_version": schema_version}
        },
        "logs": {
            log: _log_length(inputs.get(f"{INPUTS_FOLDER}/{log}"))
            for log in (IMPORT_LOG_FILE_NAME, DECISION_LOG_FILE_NAME)
        },
        "files": files,
    }
    return _StagedSet(
        files=files, manifest=(json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    )


def _publish(profile: Profile, staging: Path, name: str, staged: _StagedSet) -> Path:
    """Copy a staged set into the backups folder, manifest last, then name it.

    The copy is made under a temporary name, so the backups folder never
    holds a set under its own name before every file is in it.
    """
    publishing = profile.backup_path(name + PUBLISHING_SUFFIX)
    target = profile.backup_path(name)
    for relative in staged.files:
        _write_synced(publishing / relative, (staging / relative).read_bytes())
    _write_synced(publishing / MANIFEST_NAME, staged.manifest)
    _sync_folder(publishing)
    publishing.rename(target)
    _sync_folder(target.parent)
    return target


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
            shutil.rmtree(leftover)
    backups = profile.backup_path(".")
    if backups.is_dir():
        for child in backups.iterdir():
            stem = child.name.removesuffix(PUBLISHING_SUFFIX)
            if stem != child.name and _set_time(stem) is not None:
                shutil.rmtree(profile.backup_path(child.name))


def back_up(lock: WriterLock, *, now: datetime) -> BackupSet:
    """Write one complete backup set under the held writer lock.

    `now` names the set; the caller reads the clock, so this never does.
    """
    profile = lock.profile
    _remove_interrupted(profile)
    name = _set_name(now)
    staging = profile.backup_staging / name
    staged = _stage(profile, staging, now)
    path = _publish(profile, staging, name, staged)
    shutil.rmtree(staging)
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
