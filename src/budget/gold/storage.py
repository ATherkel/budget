# Copyright 2026 Therkel
"""The Gold stage store: its file, its migrations and its guards.

The runner, the numbered SQL files under `budget/migrations/gold/` inside the
installed package, and every refusal around them come from the generic store
runner (`budget.sqlstore`). This module names the Gold stage. Registering it
with `budget migrate` and the backup sets is issue #257's.
"""

import sqlite3
from pathlib import Path
from typing import Final

from budget.profiles import Profile
from budget.sqlstore import StageStore, migrate_store, open_store_connection

GOLD_STAGE: Final = "gold"
_MIGRATIONS_FOLDER: Final = (
    Path(__file__).resolve().parent.parent / "migrations" / "gold"
)


def migrate_gold(profile: Profile) -> None:
    """Create or upgrade the Gold store that one profile names.

    The production profile is refused before any folder or file is touched:
    it is migrated only by `budget migrate`, which backs the store up first.
    """
    migrate_store(gold_stage(profile))


def gold_stage(profile: Profile) -> StageStore:
    """Name the Gold store one profile describes."""
    return StageStore(
        profile=profile,
        stage=GOLD_STAGE,
        label="Gold",
        path=profile.gold_store,
        migrations=_MIGRATIONS_FOLDER,
    )


def open_gold_connection(
    profile: Profile, *, read_only: bool = False
) -> sqlite3.Connection:
    """Open an existing Gold store, refusing anything it cannot vouch for."""
    return open_store_connection(gold_stage(profile), read_only=read_only)
