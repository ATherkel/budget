# Copyright 2026 Therkel
"""Migrating a profile's stores, with production's backups around it.

In production, a migration that changes an existing store begins only once a
verified backup set of it is published, and a backup set follows every
migration that changed anything. Development and test profiles migrate
without backups: only production writes backup sets.
"""

from collections.abc import Callable
from datetime import UTC, datetime

from budget.backups import back_up, require_supported_stores
from budget.bronze import migrate_bronze
from budget.locking import WriterLock
from budget.profiles import PRODUCTION_PROFILE_NAME


def _utc_now() -> datetime:
    """Read the clock, in UTC."""
    return datetime.now(UTC)


def migrate_profile(
    lock: WriterLock,
    *,
    new_store: bool = False,
    clock: Callable[[], datetime] = _utc_now,
) -> None:
    """Create or upgrade the locked profile's stores: Bronze, for now.

    `new_store` asks for a new production store where none exists. `clock`
    names each backup set.
    """
    profile = lock.profile
    if profile.name != PRODUCTION_PROFILE_NAME:
        migrate_bronze(profile)
        return
    require_supported_stores(profile)

    def back_up_first() -> None:
        back_up(lock, now=clock())

    if migrate_bronze(profile, new_store=new_store, before_migrating=back_up_first):
        back_up(lock, now=clock())
