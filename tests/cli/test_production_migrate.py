# Copyright 2026 Therkel
"""`budget migrate` in production: a verified backup set first, always.

Each production profile here is a synthetic profile file in a temporary
folder, whose stores, inputs and backups stay inside it. No test opens a real
production store. Every test passes `main` an explicit environment.
"""

import shutil
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
from budget.silver import SilverStore
from tests.backups.sets import manifest, run_ids, tables, user_version
from tests.bronze.migration_resources import (
    MIGRATIONS,
    SILVER_MIGRATIONS,
    added_migration,
    added_migrations,
)
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


def _schema_version(set_folder: Path, stage: str = "bronze") -> object:
    """The schema version a set's manifest records for one stage's store."""
    stores = manifest(set_folder)["stores"]
    assert isinstance(stores, dict)
    return stores[stage]["schema_version"]


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
            with BronzeStore(production), SilverStore(production):
                pass
            (backup,) = complete_backup_sets(production)
            assert run_ids(backup.path / "bronze.db") == []
            assert user_version(backup.path / "silver.db") == 1
            assert manifest(backup.path)["profile"] == "production"
            assert manifest(backup.path)["stores"] == {
                "bronze": {"path": "bronze.db", "schema_version": 1},
                "silver": {"path": "silver.db", "schema_version": 1},
            }

    def test_silver_is_refused_where_production_has_no_bronze_store(self) -> None:
        # Every set holds Bronze, so a Silver store started alone could never
        # be backed up.
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")

            status, stderr = migrate(profile_file, "--stage", "silver", "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "budget migrate --stage bronze --new-store" in stderr
            assert not (folder / "stores").exists()
            assert not (folder / "backups").exists()

    def test_a_store_an_interrupted_start_left_empty_is_started_with_the_rest(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            production = load_profile_file(profile_file)
            # What a first `--new-store` cut off inside Bronze's migration
            # leaves: a WAL-mode file at schema version 0, with no tables.
            production.stores.mkdir(parents=True)
            with closing(sqlite3.connect(production.bronze_store)) as store:
                store.execute("PRAGMA journal_mode = WAL")

            assert migrate(profile_file, "--new-store") == (EXIT_OK, "")

            with BronzeStore(production), SilverStore(production):
                pass
            assert len(complete_backup_sets(production)) == 1

    def test_silver_is_refused_beside_a_bronze_store_left_empty(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            production = load_profile_file(profile_file)
            production.stores.mkdir(parents=True)
            with closing(sqlite3.connect(production.bronze_store)) as store:
                store.execute("PRAGMA journal_mode = WAL")

            status, stderr = migrate(profile_file, "--stage", "silver", "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "budget migrate --stage bronze --new-store" in stderr
            assert not production.silver_store.exists()
            assert not (folder / "backups").exists()

    def test_new_stores_are_refused_before_any_starts_where_one_exists(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            # Bronze's store and every set are gone; Silver's store is not.
            for lost in production.stores.glob("bronze.db*"):
                lost.unlink()
            shutil.rmtree(folder / "backups")

            status, stderr = migrate(profile_file, "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "is already a Silver store" in stderr
            assert not production.bronze_store.exists()
            assert complete_backup_sets(production) == ()

    def test_a_new_store_is_refused_where_one_exists(self) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)
            files = sorted(path.name for path in production.stores.iterdir())

            status, stderr = migrate(profile_file, "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "without --new-store" in stderr
            assert complete_backup_sets(production) == sets
            # A refusal reads the stores, and leaves no file of its own.
            assert sorted(path.name for path in production.stores.iterdir()) == files

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

    def test_a_store_left_empty_is_refused_anew_where_a_set_holds_one(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)
            # The store is lost, and an empty file at version 0 stands in
            # its place, as an interrupted start would leave it.
            for lost in production.stores.glob("bronze.db*"):
                lost.unlink()
            with closing(sqlite3.connect(production.bronze_store)) as store:
                store.execute("PRAGMA journal_mode = WAL")

            status, stderr = migrate(profile_file, "--stage", "bronze", "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "Bronze store must be restored" in stderr
            assert user_version(production.bronze_store) == 0
            assert complete_backup_sets(production) == sets

    def test_a_new_silver_store_is_refused_where_a_backup_set_holds_one(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)
            # Silver's store is lost, but the set that holds it is not.
            for lost in production.stores.glob("silver.db*"):
                lost.unlink()

            status, stderr = migrate(profile_file, "--stage", "silver", "--new-store")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "Silver store must be restored" in stderr
            assert not production.silver_store.exists()
            assert complete_backup_sets(production) == sets


class SilverBesideBronzeTests(unittest.TestCase):
    """A production profile whose stores and sets predate Silver's backups."""

    def test_silver_is_started_beside_an_existing_bronze_store_when_asked(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            started = migrate(profile_file, "--stage", "bronze", "--new-store")
            assert started[0] == EXIT_OK
            production = load_profile_file(profile_file)
            (bronze_only,) = complete_backup_sets(production)

            status, stderr = migrate(profile_file, "--stage", "silver", "--new-store")

            assert (status, stderr) == (EXIT_OK, "")
            with SilverStore(production):
                pass
            newest, older = complete_backup_sets(production)
            assert older == bronze_only
            assert manifest(newest.path)["stores"] == {
                "bronze": {"path": "bronze.db", "schema_version": 1},
                "silver": {"path": "silver.db", "schema_version": 1},
            }

    def test_a_missing_silver_store_is_refused_before_bronze_changes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            started = migrate(profile_file, "--stage", "bronze", "--new-store")
            assert started[0] == EXIT_OK
            production = load_profile_file(profile_file)
            sets = complete_backup_sets(production)

            with added_migration(ADDED_TABLE):
                status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            # `--new-store` alone would be refused: Bronze's store exists.
            assert "budget migrate --stage silver --new-store" in stderr
            assert user_version(production.bronze_store) == 1
            assert not production.silver_store.exists()
            assert complete_backup_sets(production) == sets


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

    def test_an_older_silver_store_is_backed_up_before_and_after_it_is_migrated(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)

            with added_migration(ADDED_TABLE, folder=SILVER_MIGRATIONS):
                assert migrate(profile_file) == (EXIT_OK, "")
                after, before, _ = complete_backup_sets(production)

            assert user_version(production.silver_store) == 2
            assert user_version(before.path / "silver.db") == 1
            assert "marker" not in tables(before.path / "silver.db")
            assert user_version(after.path / "silver.db") == 2
            assert "marker" in tables(after.path / "silver.db")
            assert _schema_version(before.path, "silver") == 1
            assert _schema_version(after.path, "silver") == 2
            assert _schema_version(after.path) == 1

    def test_older_stores_of_both_stages_share_one_set_before_and_one_after(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)

            both = {MIGRATIONS: ADDED_TABLE, SILVER_MIGRATIONS: ADDED_TABLE}
            with added_migrations(both):
                assert migrate(profile_file) == (EXIT_OK, "")
                after, before, _ = complete_backup_sets(production)

            for stage in ("bronze", "silver"):
                assert _schema_version(before.path, stage) == 1
                assert _schema_version(after.path, stage) == 2
            assert not production.recovery_sets_file.exists()


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
            with closing(sqlite3.connect(production.stores / "gold.db")) as store:
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
                "gold.db",
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


class RecoveryFileTests(unittest.TestCase):
    def test_an_unreadable_recovery_file_stops_the_migration_before_the_schema_changes(
        self,
    ) -> None:
        # decision 7: a recovery-sets.json this code cannot read must never
        # be quietly replaced, so the migration it would guard has to stop
        # before the store's schema changes, with the usual exit 4.
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            production.recovery_sets_file.parent.mkdir(parents=True, exist_ok=True)
            production.recovery_sets_file.write_bytes(b"not json")

            with added_migration(ADDED_TABLE):
                status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "recovery-sets.json" in stderr
            assert user_version(production.bronze_store) == 1
            assert "marker" not in tables(production.bronze_store)
            assert production.recovery_sets_file.read_bytes() == b"not json"


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
