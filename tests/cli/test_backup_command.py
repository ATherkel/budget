# Copyright 2026 Therkel
"""`budget backup`: write one backup set of production by hand.

Each profile here is a synthetic profile file in a temporary folder. Every
test passes `main` an explicit environment.
"""

import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import complete_backup_sets
from budget.profiles import load_profile_file
from tests.backups.sets import manifest
from tests.cli.commands import backup, migrate
from tests.cli.profile_files import write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


class BackupCommandTests(unittest.TestCase):
    def test_backup_writes_a_set_of_production_and_names_it(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)

            status, stdout, stderr = backup(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            newest, _ = complete_backup_sets(production)
            assert stdout == f"backup set {newest.name} written\n"

    def test_backup_is_refused_for_a_profile_that_writes_no_sets(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory))
            assert migrate(profile_file)[0] == EXIT_OK

            status, stdout, stderr = backup(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "writes no backup sets" in stderr

    def test_backup_is_refused_where_a_store_its_sets_hold_is_lost(self) -> None:
        # A set without it would claim a complete copy of a profile that has
        # lost a store, and retention would in time prune the sets holding it.
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)
            for lost in production.stores.glob("silver.db*"):
                lost.unlink()

            status, stdout, stderr = backup(profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "Silver store must be restored" in stderr
            assert complete_backup_sets(production) == sets

    def test_backup_leaves_out_a_silver_store_an_interrupted_start_left_empty(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            started = migrate(profile_file, "--stage", "bronze", "--new-store")
            assert started[0] == EXIT_OK
            production = load_profile_file(profile_file)
            # What a first `--stage silver --new-store` cut off inside Silver's
            # migration leaves: a WAL-mode file at schema version 0, no tables.
            with closing(sqlite3.connect(production.silver_store)) as store:
                store.execute("PRAGMA journal_mode = WAL")

            status, _, stderr = backup(profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            newest, _ = complete_backup_sets(production)
            assert manifest(newest.path)["stores"] == {
                "bronze": {"path": "bronze.db", "schema_version": 1},
            }

    def test_backup_is_refused_where_production_has_no_store(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _, stderr = backup(write_profile(folder, name="production"))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "no Bronze store" in stderr
            assert not (folder / "backups").exists()


if __name__ == "__main__":
    unittest.main()
