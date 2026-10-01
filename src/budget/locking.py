# Copyright 2026 Therkel
"""The profile's writer lock: one writing command at a time."""

from collections.abc import Iterator
from contextlib import contextmanager

from budget.profiles import Profile


@contextmanager
def writer_lock(profile: Profile) -> Iterator[None]:
    """Hold the profile's writer lock for the length of a `with` block."""
    raise NotImplementedError
