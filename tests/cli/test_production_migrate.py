# Copyright 2026 Therkel
"""`budget migrate` in production: a verified backup set first, always.

Each production profile here is a synthetic profile file in a temporary
folder, whose stores, inputs and backups stay inside it. No test opens a real
production store. Every test passes `main` an explicit environment.
"""

import sqlite3
import unittest
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.backups import back_up, complete_backup_sets
from budget.bronze import BronzeStore
from budget.bronze.storage import ForeignKeyViolationError
from budget.locking import writer_lock
from budget.profiles import Profile, load_profile_file
from tests.backups.sets import manifest, run_ids, tables, user_version
from tests.bronze.migration_resources import added_migration
from tests.cli.commands import migrate
from tests.cli.profile_files import write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
EXIT_VERIFICATION_FAILED = 5
# A synthetic second migration: a table the first one never makes.
ADDED_TABLE = "CREATE TABLE marker (x TEXT) STRICT;\n"
# A synthetic second migration that fails its foreign-key check.
_ORPHAN_SOURCE_RECORD = (
    "INSERT INTO source_records (payload_id, record_ordinal, fields)"
    " VALUES ('missing-payload', 1, '{}');\n"
)
KEEP_ONLY_THE_NEWEST = (
    "\n[backups]\nkeep_all_days = 0\nkeep_daily_days = 0\nkeep_monthly = 0\n"
)


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


class FailedBackupTests(unittest.TestCase):
    def test_a_backup_that_fails_leaves_the_store_unmigrated(self) -> None:
        def staging_blocked(production: Profile) -> None:
            # The first backup left its staging folder empty; a file takes its place.
            production.backup_staging.rmdir()
            production.backup_staging.write_bytes(b"not a folder")

        def log_damaged(production: Profile) -> None:
            production.import_log_file.parent.mkdir(parents=True, exist_ok=True)
            production.import_log_file.write_bytes(b"\n")

        def another_store(production: Profile) -> None:
            with closing(sqlite3.connect(production.stores / "silver.db")) as store:
                store.execute("CREATE TABLE marker (x TEXT)")

        cases = {
            "a staging folder that cannot be made": (
                staging_blocked,
                EXIT_REFUSED_ENVIRONMENT,
                "nothing was published",
            ),
            "an import log that disagrees with Bronze": (
                log_damaged,
                EXIT_VERIFICATION_FAILED,
                "imports.jsonl",
            ),
            "a store no backup set covers": (
                another_store,
                EXIT_REFUSED_ENVIRONMENT,
                "silver.db",
            ),
        }
        for case, (break_backup, expected_status, message) in cases.items():
            with self.subTest(case), TemporaryDirectory() as directory:
                profile_file = write_profile(Path(directory), name="production")
                assert migrate(profile_file, "--new-store")[0] == EXIT_OK
                production = load_profile_file(profile_file)
                sets = complete_backup_sets(production)
                break_backup(production)

                with added_migration(ADDED_TABLE):
                    status, stderr = migrate(profile_file)

                assert status == expected_status
                assert message in stderr
                assert user_version(production.bronze_store) == 1
                assert "marker" not in tables(production.bronze_store)
                assert complete_backup_sets(production) == sets


class FailedMigrationTests(unittest.TestCase):
    def test_a_failed_migration_keeps_its_backup_set_until_one_succeeds(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            # A policy that keeps nothing but the newest set.
            profile_file.write_text(
                profile_file.read_text(encoding="utf-8") + KEEP_ONLY_THE_NEWEST,
                encoding="utf-8",
            )
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)

            with (
                added_migration(_ORPHAN_SOURCE_RECORD),
                pytest.raises(ForeignKeyViolationError),
            ):
                migrate(profile_file)

            # The store is as it was, and so is its backup set.
            assert user_version(production.bronze_store) == 1
            (before,) = complete_backup_sets(production)
            assert _schema_version(before.path) == 1
            with writer_lock(production) as lock:
                later = back_up(lock, now=datetime.now(UTC))
            assert complete_backup_sets(production) == (later, before)

            # Its store is then at the added version, which only this block
            # packages, so the next backup is taken inside it too.
            with added_migration(ADDED_TABLE):
                assert migrate(profile_file) == (EXIT_OK, "")
                with writer_lock(production) as lock:
                    newest = back_up(lock, now=datetime.now(UTC))

            assert complete_backup_sets(production) == (newest,)


class ContendedProductionStoreTests(unittest.TestCase):
    def test_migrate_writes_no_set_while_another_command_holds_the_lock(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)

            with added_migration(ADDED_TABLE), writer_lock(production):
                status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "another command is running" in stderr
            assert complete_backup_sets(production) == sets
            assert user_version(production.bronze_store) == 1


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
