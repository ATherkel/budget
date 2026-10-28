# Copyright 2026 Therkel
"""The `dev refresh` application operation: production's data for development.

Development reads production only through a backup set (ADR-015). Plain
`dev refresh` restores production's newest complete set into development's
`upstream` folder, read-only, and leaves development's own stores and
inputs alone (`operations.md`, *Development diverges from a stage*).
"""

import shutil
import stat
from pathlib import Path
from typing import Final

from budget.backups import BackupSet, complete_sets_in, set_store_files
from budget.locking import WriterLock
from budget.profiles import DEVELOPMENT_PROFILE_NAME, INPUTS_FOLDER, Profile

# Development's folder of production's restored stores.
UPSTREAM_FOLDER: Final = "upstream"
# Where a refresh copies a set before it replaces `upstream`.
UPSTREAM_STAGING: Final = "upstream-staging"
# The suffix of development's inputs folder while `--inputs` replaces it.
INPUTS_REPLACING_SUFFIX: Final = ".replacing"


class NotRefreshableError(RuntimeError):
    """The profile reads no production backup sets: nothing was refreshed."""

    def __init__(self, name: str) -> None:
        """Name the profile, and what dev refresh needs."""
        super().__init__(
            "dev refresh needs a development profile whose `upstream_backups` "
            f"names production's backups folder; the {name} profile is not "
            "one; nothing was refreshed"
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


def refresh(lock: WriterLock, *, inputs: bool = False) -> BackupSet:
    """Restore production's newest complete set into `upstream`, read-only.

    The copies are made in a staging folder beside it and replace the old
    `upstream` folder only once they are all made. With `inputs`,
    development's inputs are replaced by the set's too.
    """
    profile = lock.profile
    require_refreshable(profile)
    newest = complete_sets_in(Path(str(profile.upstream_backups)))[0]
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
