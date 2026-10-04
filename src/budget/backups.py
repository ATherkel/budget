# Copyright 2026 Therkel
"""Backup sets: a complete, checked copy of a profile, written whole or not at all.

A set is a folder under the profile's backups folder, named by its UTC time.
It holds a snapshot of each store taken through SQLite's backup API, a copy of
the inputs folder, and `manifest.json`, which is written last.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from budget.locking import WriterLock
from budget.profiles import Profile


@dataclass(frozen=True)
class BackupSet:
    """One complete backup set: its folder name, its folder, and its time."""

    name: str
    path: Path
    created_at: datetime


def back_up(lock: WriterLock, *, now: datetime) -> BackupSet:
    """Write one complete backup set under the held writer lock."""
    raise NotImplementedError


def complete_backup_sets(profile: Profile) -> tuple[BackupSet, ...]:
    """Return the profile's complete backup sets, newest first."""
    raise NotImplementedError
