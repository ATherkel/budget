# Copyright 2026 Therkel
"""The `status` application operation: what a report can be trusted for.

Completeness reads the current Gold publication and nothing else, with no
writer lock and no write of any kind, so a store that does not exist yet stays
absent.
"""

from dataclasses import dataclass

from budget.gold.store import GoldStore
from budget.profiles import Profile


@dataclass(frozen=True)
class Completeness:
    """The completeness of one profile; `published` is None with nothing published."""

    published: int | None


def completeness(profile: Profile) -> Completeness:
    """Read the completeness figures of the profile's current publication."""
    if not profile.gold_store.exists():
        return Completeness(published=None)
    with GoldStore(profile, read_only=True) as store:
        current = store.current()
    return Completeness(published=None if current is None else current.publication_id)
