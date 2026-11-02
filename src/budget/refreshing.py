# Copyright 2026 Therkel
"""The `dev refresh` application operation: production's data for development.

Development reads production only through a backup set (ADR-015). Plain
`dev refresh` restores production's newest complete set into development's
`upstream` folder, read-only, and leaves development's own stores and
inputs alone (`operations.md`, *Development diverges from a stage*).
"""

import shutil
import stat
from dataclasses import dataclass, replace
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
# The suffix of the old inputs folder, set aside until the new one is in place.
INPUTS_REPLACED_SUFFIX: Final = ".replaced"


class NotRefreshableError(RuntimeError):
    """The profile reads no production backup sets: nothing was refreshed."""

    def __init__(self, name: str) -> None:
        """Name the profile, and what dev refresh needs."""
        super().__init__(
            "dev refresh needs a development profile whose `upstream_backups` "
            f"names production's backups folder; the {name} profile is not "
            "one; nothing was refreshed"
        )


class NotProductionsSetError(RuntimeError):
    """The newest set in `upstream_backups` is another profile's."""

    def __init__(self, name: str, profile: str | None) -> None:
        """Name the set and whose it is."""
        super().__init__(
            f"backup set {name} is the {profile or 'unnamed'} profile's, not "
            "production's: check `upstream_backups`; nothing was refreshed"
        )


class InputsNotReplacedError(RuntimeError):
    """`--inputs` could not swap in the set's inputs: development's are intact."""

    def __init__(self, cause: OSError) -> None:
        """Say what failed; upstream was already refreshed."""
        super().__init__(
            f"could not replace development's inputs ({cause.strerror or cause}); "
            "they are unchanged, but upstream was refreshed"
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

    The copy is made beside the folder and replaces it only once whole. The
    old folder is moved aside first and deleted last, so a folder that cannot
    be moved (a file in it is open) leaves it exactly as it was.
    """
    inputs = Path(profile.inputs)
    replacing = inputs.with_name(inputs.name + INPUTS_REPLACING_SUFFIX)
    replaced = inputs.with_name(inputs.name + INPUTS_REPLACED_SUFFIX)
    shutil.rmtree(replacing, ignore_errors=True)
    shutil.rmtree(replaced, ignore_errors=True)
    try:
        shutil.copytree(backup.path / INPUTS_FOLDER, replacing)
        inputs.rename(replaced)
    except OSError as error:
        shutil.rmtree(replacing, ignore_errors=True)
        raise InputsNotReplacedError(error) from error
    replacing.rename(inputs)
    shutil.rmtree(replaced, ignore_errors=True)


@dataclass(frozen=True)
class Refreshed:
    """What `refresh` did: the set used and the newer sets passed over."""

    backup: BackupSet
    skipped: tuple[str, ...]


def refresh(lock: WriterLock, *, inputs: bool = False) -> Refreshed:
    """Restore production's newest complete set into `upstream`, read-only.

    The copies are made in a staging folder beside it and replace the old
    `upstream` folder only once they are all made. With `inputs`,
    development's inputs are replaced by the set's too.
    """
    profile = lock.profile
    require_refreshable(profile)
    # Production's stores, checked as production's: each must open under
    # its own identity, at a schema version this code knows, and intact.
    as_production = replace(profile, name=PRODUCTION_PROFILE_NAME)
    sets = complete_sets_in(Path(str(profile.upstream_backups)))
    newest, skipped = newest_readable(as_production, sets)
    taken_of = set_profile(newest)
    if taken_of != PRODUCTION_PROFILE_NAME:
        raise NotProductionsSetError(newest.name, taken_of)
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
    return Refreshed(newest, skipped)
