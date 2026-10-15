# Copyright 2026 Therkel
"""The Gold stage store: its file, its migrations and its guards.

The runner, the numbered SQL files under `budget/migrations/gold/` inside the
installed package, and every refusal around them come from the generic store
runner (`budget.sqlstore`). This module names the Gold stage.
"""

import sqlite3

from budget.profiles import Profile
from budget.sqlstore import StageStore


def migrate_gold(profile: Profile) -> None:
    """Create or upgrade the Gold store that one profile names."""
    raise NotImplementedError


def gold_stage(profile: Profile) -> StageStore:
    """Name the Gold store one profile describes."""
    raise NotImplementedError


def open_gold_connection(
    profile: Profile, *, read_only: bool = False
) -> sqlite3.Connection:
    """Open an existing Gold store, refusing anything it cannot vouch for."""
    raise NotImplementedError
