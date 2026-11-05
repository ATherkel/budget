# Copyright 2026 Therkel
"""Rebuilding Silver from Bronze inputs into the profile's store.

The build itself is the pure `budget.silver.build`, whose signature does not
change. A rebuild names its inputs once, in `SilverBuildInputs`, so the
persisted rebuild takes its one profile authority and that one value rather
than a long list of positional arguments.
"""

from budget.locking import WriterLock, writer_lock
from budget.profiles import Profile
from budget.silver.build import derive
from budget.silver.inputs import SilverBuildInputs
from budget.silver.models import SilverResult
from budget.silver.store import SilverStore


def rebuild_silver(
    profile: Profile | WriterLock,
    *,
    inputs: SilverBuildInputs,
) -> SilverResult:
    """Rebuild one profile's Silver store from Bronze inputs and return it.

    The build is the existing pure `budget.silver.build`; this function only
    replaces the stored result with what the build produced, so a rebuild is
    one transaction against `silver.db`. `profile` is the one authority for the
    profile the result belongs to, named either way: a `Profile` takes and
    releases the writer lock itself, and a `WriterLock` is a command's own
    lock, held for its whole run, which the rebuild reuses without acquiring it
    a second time.
    """
    if isinstance(profile, WriterLock):
        return _replace(profile.profile, inputs)
    with writer_lock(profile) as held:
        return _replace(held.profile, inputs)


def derive_silver(inputs: SilverBuildInputs) -> SilverResult:
    """Run the pure build over `inputs`, storing nothing."""
    return derive(inputs)


def store_silver(
    profile: Profile | WriterLock, inputs: SilverBuildInputs, result: SilverResult
) -> None:
    """Replace the stored Silver with `result`, which `inputs` derived."""
    held = profile.profile if isinstance(profile, WriterLock) else profile
    with SilverStore(held) as store:
        store.replace(result, currencies=inputs.currencies)


def _replace(profile: Profile, inputs: SilverBuildInputs) -> SilverResult:
    """Run the pure build and store exactly what it produced."""
    result = derive_silver(inputs)
    store_silver(profile, inputs, result)
    return result
