# Copyright 2026 Therkel
"""A synthetic household ready for `budget rebuild` to publish its Gold.

The profile is a development profile file in a temporary folder, migrated, with
the household's inputs written and one export imported and built into Silver.
Every account, text and amount is invented.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.rebuilding import rebuild_from_silver
from tests.cli.commands import migrate
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload

TAXONOMY = """\
format = 1

[group.food]
name = "Food"
direction = "expense"

[category.groceries]
name = "Groceries"
group = "food"
"""
RULES = "format = 1\n"
EXPORT = payload("01.03.2026")


@dataclass(frozen=True)
class Household:
    """A migrated profile with inputs, one stored import run and its Silver."""

    profile_file: Path
    profile: Profile
    import_run_id: str


def household(folder: Path) -> Household:
    """Write and migrate a profile, then import one export and build Silver."""
    profile_file = write_profile(folder)
    assert migrate(profile_file)[0] == 0
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    profile.input_file("taxonomy.toml").write_text(TAXONOMY, encoding="utf-8")
    profile.input_file("rules.toml").write_text(RULES, encoding="utf-8")
    source = drop(profile, "joint-current", "danske-20260305.csv", EXPORT)
    with writer_lock(profile) as lock:
        imported = import_inbox_file(
            lock,
            source,
            Coverage(covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)),
        )
        rebuild_from_silver(lock)
    return Household(profile_file, profile, imported.import_run.import_run_id)
