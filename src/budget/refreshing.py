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
from collections.abc import Iterable
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import Final

from budget.backups import (
    BackupSet,
    complete_sets_in,
    set_profile,
    set_store_files,
)
from budget.locking import WriterLock
from budget.profiles import (
    DEVELOPMENT_PROFILE_NAME,
    INPUTS_FOLDER,
    PRODUCTION_PROFILE_NAME,
    Profile,
)
from budget.restoring import newest_readable

# Development's folder of production's restored stores.
UPSTREAM_FOLDER: Final = "upstream"
# Where a refresh copies a set before it replaces `upstream`.
UPSTREAM_STAGING: Final = "upstream-staging"
# The suffix of development's inputs folder while `--inputs` replaces it.
INPUTS_REPLACING_SUFFIX: Final = ".replacing"
# Where `--writable` relabels a set's stores before moving them in.
WRITABLE_STAGING: Final = "writable-staging"
# Where `--writable` keeps development's old stores until the new are in.
WRITABLE_REPLACED: Final = "writable-replaced"
# A store file and the files SQLite keeps beside it.
_STORE_FILE_SUFFIXES: Final = ("", "-wal", "-shm", "-journal")


class NotRefreshableError(RuntimeError):
    """The profile reads no production backup sets: nothing was refreshed."""

    def __init__(self, name: str) -> None:
        """Name the profile, and what dev refresh needs."""
        super().__init__(
            "dev refresh needs a development profile whose `upstream_backups` "
            f"names production's backups folder; the {name} profile is not "
            "one; nothing was refreshed"
        )


class RefreshWriteError(RuntimeError):
    """A writable refresh could not move its stores in: none was changed."""

    def __init__(self, reason: str) -> None:
        """Say why, and that development's stores were kept."""
        super().__init__(
            f"the backup set could not be refreshed into development's stores: "
            f"{reason}; development's stores are as they were"
        )


class NotProductionsSetError(RuntimeError):
    """The newest set in `upstream_backups` is another profile's."""

    def __init__(self, name: str, profile: str | None) -> None:
        """Name the set and whose it is."""
        super().__init__(
            f"backup set {name} is the {profile or 'unnamed'} profile's, not "
            "production's: check `upstream_backups`; nothing was refreshed"
        )


def require_refreshable(profile: Profile) -> None:
    """Refuse, touching nothing, a profile that has no upstream sets to read."""
    if profile.name != DEVELOPMENT_PROFILE_NAME or profile.upstream_backups is None:
        raise NotRefreshableError(profile.name)


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


def _own_store_files(profile: Profile) -> list[Path]:
    """Name development's stage store files that exist, with SQLite's own."""
    stores = (profile.bronze_store, profile.silver_store, profile.gold_store)
    return [
        found
        for store in stores
        for suffix in _STORE_FILE_SUFFIXES
        if (found := store.with_name(store.name + suffix)).exists()
    ]


def _swap_in(profile: Profile, staging: Path, stores: Iterable[str]) -> None:
    """Replace development's stores with the staged ones, as one group.

    Every store there, a set's or not, is moved aside first, so no old store
    stays beside new ones. If a move in fails, the new stores are taken out
    and the old ones put back.
    """
    aside = profile.stores / WRITABLE_REPLACED
    shutil.rmtree(aside, ignore_errors=True)
    aside.mkdir()
    for found in _own_store_files(profile):
        found.replace(aside / found.name)
    try:
        for store in stores:
            (staging / store).replace(profile.stores / store)
    except OSError:
        for found in _own_store_files(profile):
            found.unlink()
        for kept in aside.iterdir():
            kept.replace(profile.stores / kept.name)
        raise
    shutil.rmtree(aside, ignore_errors=True)


def _restore_writable(profile: Profile, backup: BackupSet) -> None:
    """Restore the set into development's own stores, relabelled as its own.

    Development's stores make no promise to keep (`operations.md`), so the
    ones there are replaced; each copy is relabelled before it is moved in.
    """
    staging = profile.stores / WRITABLE_STAGING
    try:
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        stores = set_store_files(backup).values()
        for store in stores:
            shutil.copyfile(backup.path / store, staging / store)
            _relabel(staging / store, profile)
        _swap_in(profile, staging, stores)
    except OSError as error:
        raise RefreshWriteError(error.strerror or type(error).__name__) from None
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
    require_refreshable(profile)
    # Production's stores, checked as production's: each must open under
    # its own identity, at a schema version this code knows, and intact.
    as_production = replace(profile, name=PRODUCTION_PROFILE_NAME)
    sets = complete_sets_in(Path(str(profile.upstream_backups)))
    newest, _ = newest_readable(as_production, sets)
    taken_of = set_profile(newest)
    if taken_of != PRODUCTION_PROFILE_NAME:
        raise NotProductionsSetError(newest.name, taken_of)
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
