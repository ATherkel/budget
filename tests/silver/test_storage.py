# Copyright 2026 Therkel
"""The Silver store file: its migration, schema and identity.

These tests use the public `Profile` and `migrate_silver` seams. The store file
is opened directly only to check the on-disk contracts ADR-013 and ADR-015
name: `STRICT` tables, WAL, `PRAGMA user_version`, and the one-row
`store_identity` that keeps another profile, or another stage, from opening
this file.

Only the creation contract was written red. The guards below it are covered by
the shared runner (`budget.sqlstore`, written red for Bronze in
`tests/bronze/test_storage.py`), so here they are Silver regression coverage:
the same refusals, reached through `migrate_silver` and the Silver schema.
"""

import sqlite3
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget.bronze import migrate_bronze
from budget.bronze.storage import open_bronze_connection
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from budget.silver import storage
from budget.silver.storage import migrate_silver, open_silver_connection

# The whole persisted result: the identity table, the account currency
# snapshot, every collection of a Silver build, and the parent rows their
# children point at.
STORE_TABLES = {
    "account_currencies",
    "transactions",
    "transaction_evidence",
    "unbooked_records",
    "balance_observations",
    "account_evidence",
    "import_run_results",
    "validation_errors",
    "import_run_result_review_items",
    "review_items",
    "review_item_payloads",
    "store_identity",
}


@contextmanager
def _connected(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the store file directly and close it, so Windows can clean up."""
    connection = sqlite3.connect(path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


class SilverStorageTests(unittest.TestCase):
    def test_migrate_creates_a_strict_silver_store_that_records_its_identity(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            migrate_silver(profile)

            with _connected(profile.silver_store) as connection:
                definitions = dict(
                    connection.execute(
                        "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
                    )
                )
                assert set(definitions) == STORE_TABLES
                for definition in definitions.values():
                    assert "STRICT" in definition
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
                assert connection.execute(
                    "SELECT profile, stage FROM store_identity"
                ).fetchall() == [("test", "silver")]
                assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_migrating_again_changes_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            migrate_silver(profile)

            with _connected(profile.silver_store) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
                assert connection.execute(
                    "SELECT profile, stage FROM store_identity"
                ).fetchall() == [("test", "silver")]

    def test_migrate_creates_only_the_silver_store(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            migrate_silver(profile)

            assert profile.silver_store.exists()
            assert not profile.bronze_store.exists()

    def test_migrate_refuses_the_production_profile_before_touching_the_disk(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = Profile(
                name="production",
                stores=root / "production",
                inputs=root / "inputs",
                inbox=root / "inbox",
                exports=root / "exports",
            )

            with pytest.raises(storage.ProductionMigrationBlockedError):
                migrate_silver(profile)

            assert list(root.iterdir()) == []

    def test_the_sqlite_version_floor_is_checked_before_any_file_is_touched(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            with (
                mock.patch.object(sqlite3, "sqlite_version_info", (3, 45, 1)),
                pytest.raises(storage.UnsupportedSQLiteVersionError),
            ):
                migrate_silver(profile)

            assert not profile.silver_store.exists()

    def test_migrate_refuses_a_store_of_another_profile(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_test_profile(root)
            migrate_silver(profile)
            other = Profile(
                name="development",
                stores=profile.stores,
                inputs=profile.inputs,
                inbox=profile.inbox,
                exports=profile.exports,
                root=root,
            )

            with pytest.raises(storage.StoreIdentityError):
                migrate_silver(other)

    def test_migrate_refuses_an_unversioned_store_and_keeps_its_rows(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            profile.silver_store.parent.mkdir(parents=True)
            with _connected(profile.silver_store) as connection:
                connection.execute("CREATE TABLE legacy (kept TEXT)")
                connection.execute("INSERT INTO legacy (kept) VALUES ('keep me')")

            with pytest.raises(storage.UnversionedStoreError):
                migrate_silver(profile)

            with _connected(profile.silver_store) as connection:
                assert connection.execute("SELECT kept FROM legacy").fetchall() == [
                    ("keep me",)
                ]
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 0

    def test_migrate_refuses_a_store_whose_version_was_lost(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            with _connected(profile.silver_store) as connection:
                connection.execute("PRAGMA user_version = 0")

            with pytest.raises(storage.UnversionedStoreError):
                migrate_silver(profile)

    def test_migrate_refuses_a_newer_schema_version(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            with _connected(profile.silver_store) as connection:
                connection.execute("PRAGMA user_version = 99")

            with pytest.raises(storage.UnsupportedStoreVersionError):
                migrate_silver(profile)

    def test_a_file_that_is_not_a_store_is_refused_without_changing_it(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            profile.silver_store.parent.mkdir(parents=True)
            profile.silver_store.write_bytes(b"this is not a database")

            with pytest.raises(sqlite3.DatabaseError):
                migrate_silver(profile)

            assert profile.silver_store.read_bytes() == b"this is not a database"

    def test_a_store_path_with_url_characters_still_migrates(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = Profile(
                name="test",
                stores=root / "store #1 & more",
                inputs=root / "inputs",
                inbox=root / "inbox",
                exports=root / "exports",
                root=root,
            )

            migrate_silver(profile)

            assert profile.silver_store.exists()

    def test_a_silver_store_cannot_record_another_stage(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with (
                _connected(profile.silver_store) as connection,
                pytest.raises(sqlite3.IntegrityError),
            ):
                connection.execute(
                    "INSERT INTO store_identity (profile, stage)"
                    " VALUES ('test', 'bronze')"
                )

    def test_the_bronze_and_silver_stores_are_separate_files(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_bronze(profile)

            migrate_silver(profile)

            assert profile.bronze_store.read_bytes() != b""
            assert profile.silver_store.read_bytes() != b""
            assert profile.bronze_store != profile.silver_store

    def test_opening_a_migrated_store_sets_the_connection_pragmas(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            connection = open_silver_connection(profile)
            try:
                assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
                assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
                # Synchronous 2 is FULL.
                assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
            finally:
                connection.close()

    def test_open_refuses_a_store_that_was_never_migrated(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            with pytest.raises(storage.StoreNotFoundError) as refusal:
                open_silver_connection(profile)

            # The refusal names the stage that has no store, not just the path.
            assert "no Silver store at" in str(refusal.value)
            assert not profile.silver_store.exists()

    def test_open_refuses_a_store_from_another_profile(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_test_profile(root)
            migrate_silver(profile)
            other = Profile(
                name="development",
                stores=profile.stores,
                inputs=profile.inputs,
                inbox=profile.inbox,
                exports=profile.exports,
                root=root,
            )

            with pytest.raises(storage.StoreIdentityError):
                open_silver_connection(other)

    def test_open_refuses_a_store_whose_version_was_lost(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            with _connected(profile.silver_store) as connection:
                connection.execute("PRAGMA user_version = 0")

            with pytest.raises(storage.MigrationRequiredError):
                open_silver_connection(profile)

    def test_open_refuses_a_newer_schema_version(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)
            with _connected(profile.silver_store) as connection:
                connection.execute("PRAGMA user_version = 99")

            with pytest.raises(storage.UnsupportedStoreVersionError):
                open_silver_connection(profile)

    def test_the_sqlite_version_floor_is_checked_before_opening(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_silver(profile)

            with (
                mock.patch.object(sqlite3, "sqlite_version_info", (3, 45, 1)),
                pytest.raises(storage.UnsupportedSQLiteVersionError),
            ):
                open_silver_connection(profile)

    def test_each_stage_opens_only_its_own_file(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_bronze(profile)

            # A migrated Bronze store does not stand in for Silver.
            with pytest.raises(storage.StoreNotFoundError):
                open_silver_connection(profile)

            migrate_silver(profile)

            open_bronze_connection(profile).close()
            open_silver_connection(profile).close()


if __name__ == "__main__":
    unittest.main()
