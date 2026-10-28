# Copyright 2026 Therkel
"""The `dev refresh` application operation: production's data for development.

Development reads production only through a backup set (ADR-015). Plain
`dev refresh` restores production's newest complete set into development's
`upstream` folder, read-only, and leaves development's own stores and
inputs alone (`operations.md`, *Development diverges from a stage*).
"""

import shutil
import sqlite3
import stat
from contextlib import closing
from pathlib import Path
from typing import Final

from budget.backups import BackupSet, complete_sets_in, set_store_files
from budget.locking import WriterLock
from budget.profiles import INPUTS_FOLDER, Profile

# Development's folder of production's restored stores.
UPSTREAM_FOLDER: Final = "upstream"
# Where a refresh copies a set before it replaces `upstream`.
UPSTREAM_STAGING: Final = "upstream-staging"
# The suffix of development's inputs folder while `--inputs` replaces it.
INPUTS_REPLACING_SUFFIX: Final = ".replacing"
# Where `--writable` relabels a set's stores before moving them in.
WRITABLE_STAGING: Final = "writable-staging"
# A store file and the files SQLite keeps beside it.
_STORE_FILE_SUFFIXES: Final = ("", "-wal", "-shm", "-journal")


def _remove_read_only(folder: Path) -> None:
    """Delete a folder of read-only copies, making each writable first."""
    if not folder.is_dir():
        return
    for copy in folder.iterdir():
        copy.chmod(stat.S_IREAD | stat.S_IWRITE)
    shutil.rmtree(folder)


def _replace_inputs(profile: Profile, backup: BackupSet) -> None:
    """Make development's inputs folder the set's copy of production's.

    The copy is made beside the folder and replaces it only once whole.
    """
    inputs = Path(profile.inputs)
    replacing = inputs.with_name(inputs.name + INPUTS_REPLACING_SUFFIX)
    shutil.rmtree(replacing, ignore_errors=True)
    shutil.copytree(backup.path / INPUTS_FOLDER, replacing)
    shutil.rmtree(inputs, ignore_errors=True)
    replacing.rename(inputs)


def _relabel(copy: Path, profile: Profile) -> None:
    """Make a copy of production's store development's, changing nothing else.

    Only the one-row `store_identity` changes, so Bronze's runs and payloads,
    its evidence, come over exactly as production recorded them.
    """
    with closing(sqlite3.connect(copy)) as connection, connection:
        connection.execute("UPDATE store_identity SET profile = ?", (profile.name,))


def _restore_writable(profile: Profile, backup: BackupSet) -> None:
    """Restore the set into development's own stores, relabelled as its own.

    Development's stores make no promise to keep (`operations.md`), so the
    ones there are replaced; each copy is relabelled before it is moved in.
    """
    staging = profile.stores / WRITABLE_STAGING
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        stores = set_store_files(backup).values()
        for store in stores:
            shutil.copyfile(backup.path / store, staging / store)
            _relabel(staging / store, profile)
        for store in stores:
            for suffix in _STORE_FILE_SUFFIXES:
                (profile.stores / f"{store}{suffix}").unlink(missing_ok=True)
            (staging / store).replace(profile.stores / store)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def refresh(
    lock: WriterLock, *, inputs: bool = False, writable: bool = False
) -> BackupSet:
    """Restore production's newest complete set into `upstream`, read-only.

    The copies are made in a staging folder beside it and replace the old
    `upstream` folder only once they are all made. With `inputs`,
    development's inputs are replaced by the set's too. With `writable`, the
    set is restored into development's own stores instead of `upstream`.
    """
    profile = lock.profile
    newest = complete_sets_in(Path(str(profile.upstream_backups)))[0]
    if writable:
        _restore_writable(profile, newest)
        if inputs:
            _replace_inputs(profile, newest)
        return newest
    upstream = profile.stores / UPSTREAM_FOLDER
    staging = profile.stores / UPSTREAM_STAGING
    _remove_read_only(staging)
    staging.mkdir(parents=True)
    for store in set_store_files(newest).values():
        copy = staging / store
        shutil.copyfile(newest.path / store, copy)
        copy.chmod(stat.S_IREAD)
    _remove_read_only(upstream)
    staging.rename(upstream)
    if inputs:
        _replace_inputs(profile, newest)
    return newest
