# Copyright 2026 Therkel
"""`budget restore`: put a whole profile back from one complete backup set.

Each profile here is a synthetic production profile file in a temporary
folder, whose stores are deleted as a machine that died would lose them.
Every test passes `main` an explicit environment.
"""

import shutil
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import BackupSet, back_up, complete_backup_sets
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from tests.backups.sets import import_one, run_ids, tables
from tests.cli.commands import migrate, restore
from tests.cli.profile_files import write_profile
from tests.importing.households import ACCOUNTS

EXIT_OK = 0


def _production_with_a_set(folder: Path) -> tuple[Path, Profile, BackupSet, str]:
    """Start production, import one run, and back it up; return what was made."""
    profile_file = write_profile(folder, name="production")
    assert migrate(profile_file, "--new-store")[0] == EXIT_OK
    production = load_profile_file(profile_file)
    production.inputs.mkdir()
    production.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    with writer_lock(production) as lock:
        run_id = import_one(lock)
        # After the set `migrate` wrote, so it is the newest.
        written = back_up(lock, now=datetime.now(UTC))
    return profile_file, production, written, run_id


class RestoreCommandTests(unittest.TestCase):
    def test_restore_puts_every_store_of_the_newest_set_into_an_empty_profile(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, run_id = _production_with_a_set(
                Path(directory)
            )
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == f"restored backup set {written.name}\n"
            assert run_ids(production.bronze_store) == [run_id]
            for store in ("silver.db", "gold.db"):
                assert tables(production.stores / store) == tables(written.path / store)

    def test_restore_takes_the_set_it_is_given_by_name(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file, production, written, _ = _production_with_a_set(
                Path(directory)
            )
            older = next(
                found
                for found in complete_backup_sets(production)
                if found.name != written.name
            )
            shutil.rmtree(production.stores)

            status, stdout, stderr = restore(profile_file, older.name)

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout == f"restored backup set {older.name}\n"
            # The set `migrate` wrote holds no import run yet.
            assert run_ids(production.bronze_store) == []
