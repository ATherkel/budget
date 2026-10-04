# Copyright 2026 Therkel
"""`budget migrate` in production: a verified backup set first, always.

Each production profile here is a synthetic profile file in a temporary
folder, whose stores, inputs and backups stay inside it. No test opens a real
production store. Every test passes `main` an explicit environment.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import complete_backup_sets
from budget.bronze import BronzeStore
from budget.profiles import load_profile_file
from tests.backups.sets import manifest, run_ids, tables, user_version
from tests.bronze.migration_resources import added_migration
from tests.cli.commands import migrate
from tests.cli.profile_files import write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
# A synthetic second migration: a table the first one never makes.
ADDED_TABLE = "CREATE TABLE marker (x TEXT) STRICT;\n"


def _schema_version(set_folder: Path) -> object:
    """The Bronze schema version a set's manifest records."""
    stores = manifest(set_folder)["stores"]
    assert isinstance(stores, dict)
    return stores["bronze"]["schema_version"]


class NewProductionStoreTests(unittest.TestCase):
    def test_a_new_store_is_started_only_when_asked_and_then_backed_up(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")

            status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "--new-store" in stderr
            assert not (folder / "stores").exists()
            assert not (folder / "backups").exists()

            status, stderr = migrate(profile_file, "--new-store")

            assert (status, stderr) == (EXIT_OK, "")
            production = load_profile_file(profile_file)
            with BronzeStore(production):
                pass
            (backup,) = complete_backup_sets(production)
            assert run_ids(backup.path / "bronze.db") == []
            assert manifest(backup.path)["profile"] == "production"

    def test_a_new_store_is_refused_where_one_exists(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)

            status, stderr = migrate(profile_file, "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "without --new-store" in stderr
            assert complete_backup_sets(production) == sets

    def test_a_new_store_is_refused_where_backup_sets_could_restore_one(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            # The store is lost, but its backup sets are not.
            for lost in production.stores.glob("bronze.db*"):
                lost.unlink()

            status, stderr = migrate(profile_file, "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "restore" in stderr
            assert not production.bronze_store.exists()


class OlderProductionStoreTests(unittest.TestCase):
    def test_an_older_store_is_backed_up_before_and_after_it_is_migrated(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)

            with added_migration(ADDED_TABLE):
                assert migrate(profile_file) == (EXIT_OK, "")
                after, before, _ = complete_backup_sets(production)

            assert user_version(production.bronze_store) == 2
            assert user_version(before.path / "bronze.db") == 1
            assert "marker" not in tables(before.path / "bronze.db")
            assert user_version(after.path / "bronze.db") == 2
            assert "marker" in tables(after.path / "bronze.db")
            assert _schema_version(before.path) == 1
            assert _schema_version(after.path) == 2


class CurrentProductionStoreTests(unittest.TestCase):
    def test_a_store_already_current_is_left_as_it_is_without_a_new_set(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)

            assert migrate(profile_file) == (EXIT_OK, "")

            assert complete_backup_sets(production) == sets


if __name__ == "__main__":
    unittest.main()
