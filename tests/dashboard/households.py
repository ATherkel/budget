# Copyright 2026 Therkel
"""A test household whose dashboard is ready: Gold migrated, passphrase set."""

from dataclasses import replace
from pathlib import Path

from budget.dashboard import set_passphrase
from budget.gold.storage import migrate_gold
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile

HOUSEHOLD_PHRASE = "correct horse battery staple"


def dashboard_profile(root: Path) -> Profile:
    """Return a test profile in `root` with Gold migrated and the phrase set."""
    profile = replace(
        make_test_profile(root), passphrase_file=root / "dashboard-passphrase"
    )
    migrate_gold(profile)
    set_passphrase(profile, HOUSEHOLD_PHRASE)
    return profile
