# Copyright 2026 Therkel
"""The Bronze store file: migration, identity, versions and refusals.

These tests use the public `Profile`, `migrate_bronze` and `BronzeStore` seams.
The store file is opened directly only to check the on-disk contracts the
storage decision names: `STRICT` tables, WAL, `PRAGMA user_version`, the
one-row `store_identity`, and what a refused migration leaves behind.
"""

import sqlite3
import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget.bronze import BronzeStore, migrate_bronze, storage
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile


@contextmanager
def _connected(path: Path) -> Iterator[sqlite3.Connection]:
    """Open the store file directly and close it, so Windows can clean up."""
    connection = sqlite3.connect(path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def _tables(path: Path) -> set[str]:
    with _connected(path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {row[0] for row in rows}


@contextmanager
def _patched_resources(suffix: str) -> Iterator[None]:
    """Patch the stdlib read boundary so the real resource gains a suffix.

    Discovery, the loader, the runner, the transaction and the foreign-key check
    all stay the real code; only `pathlib.Path.read_text` is replaced, and only
    for the packaged `0001` file, which is returned with `suffix` appended.
    """
    original = Path.read_text

    def read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        text = original(path, encoding, errors)
        if path.name.startswith("0001_"):
            return text + suffix
        return text

    with mock.patch.object(Path, "read_text", autospec=True, side_effect=read_text):
        yield


class BronzeStorageTests(unittest.TestCase):
    def test_migrate_creates_a_strict_store_that_records_its_identity(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            migrate_bronze(profile)

            with _connected(profile.bronze_store) as connection:
                definitions = dict(
                    connection.execute(
                        "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
                    )
                )
                assert set(definitions) == {
                    "raw_payloads",
                    "import_runs",
                    "source_records",
                    "format_failures",
                    "store_identity",
                }
                for definition in definitions.values():
                    assert "STRICT" in definition
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
                assert connection.execute(
                    "SELECT profile, stage FROM store_identity"
                ).fetchall() == [("test", "bronze")]
                assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_migrating_again_changes_nothing_and_the_store_still_opens(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_bronze(profile)

            migrate_bronze(profile)

            with BronzeStore(profile) as store:
                assert store.get_format_failures("missing") == ()

    def test_migrate_refuses_the_production_profile_before_touching_the_disk(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = Profile(
                name="production",
                stores=root / "production",
                inputs=root / "inputs",
            )

            with pytest.raises(storage.ProductionMigrationBlockedError):
                migrate_bronze(profile)

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
                migrate_bronze(profile)
            with (
                mock.patch.object(sqlite3, "sqlite_version_info", (3, 45, 1)),
                pytest.raises(storage.UnsupportedSQLiteVersionError),
            ):
                BronzeStore(profile)

            assert not profile.bronze_store.exists()

    def test_open_refuses_a_store_that_was_never_migrated(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            with pytest.raises(storage.StoreNotFoundError):
                BronzeStore(profile)

            assert not profile.bronze_store.exists()

    def test_open_refuses_a_store_from_another_profile(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_test_profile(root)
            migrate_bronze(profile)
            other = Profile(
                name="development",
                stores=profile.stores,
                inputs=profile.inputs,
                root=root,
            )

            with pytest.raises(storage.StoreIdentityError):
                BronzeStore(other)
            with pytest.raises(storage.StoreIdentityError):
                migrate_bronze(other)

    def test_a_store_cannot_record_another_stage(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_bronze(profile)

            with (
                _connected(profile.bronze_store) as connection,
                pytest.raises(sqlite3.IntegrityError),
            ):
                connection.execute(
                    "INSERT INTO store_identity (profile, stage)"
                    " VALUES ('test', 'silver')"
                )

    def test_open_refuses_a_newer_schema_version(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_bronze(profile)
            with _connected(profile.bronze_store) as connection:
                connection.execute("PRAGMA user_version = 99")

            with pytest.raises(storage.UnsupportedStoreVersionError):
                BronzeStore(profile)
            with pytest.raises(storage.UnsupportedStoreVersionError):
                migrate_bronze(profile)

    def test_open_refuses_a_store_whose_version_was_lost(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_bronze(profile)
            with _connected(profile.bronze_store) as connection:
                connection.execute("PRAGMA user_version = 0")

            with pytest.raises(storage.MigrationRequiredError):
                BronzeStore(profile)
            with pytest.raises(storage.UnversionedStoreError):
                migrate_bronze(profile)

    def test_migrate_refuses_an_unversioned_store_and_keeps_its_rows(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            profile.bronze_store.parent.mkdir(parents=True)
            with _connected(profile.bronze_store) as connection:
                connection.execute("CREATE TABLE legacy (kept TEXT)")
                connection.execute("INSERT INTO legacy (kept) VALUES ('keep me')")

            with pytest.raises(storage.UnversionedStoreError):
                migrate_bronze(profile)

            with _connected(profile.bronze_store) as connection:
                assert connection.execute("SELECT kept FROM legacy").fetchall() == [
                    ("keep me",)
                ]
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
            assert _tables(profile.bronze_store) == {"legacy"}

    def test_a_file_that_is_not_a_store_is_refused_without_changing_it(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            profile.bronze_store.parent.mkdir(parents=True)
            profile.bronze_store.write_bytes(b"this is not a database")

            with pytest.raises(sqlite3.DatabaseError):
                migrate_bronze(profile)

            assert profile.bronze_store.read_bytes() == b"this is not a database"

    def test_a_store_path_with_url_characters_still_opens(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = Profile(
                name="test",
                stores=root / "store #1 & more",
                inputs=root / "inputs",
                root=root,
            )

            migrate_bronze(profile)

            with BronzeStore(profile) as store:
                assert store.get_source_records("absent") == ()

    def test_opening_a_store_sets_the_connection_pragmas(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            migrate_bronze(profile)

            connection = storage.open_bronze_connection(profile)
            try:
                assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
                assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
                # Synchronous 2 is FULL.
                assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
            finally:
                connection.close()

    def test_an_empty_file_with_a_future_version_is_not_touched(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            profile.bronze_store.parent.mkdir(parents=True)
            with _connected(profile.bronze_store) as connection:
                connection.execute("PRAGMA user_version = 99")

            with pytest.raises(storage.UnsupportedStoreVersionError):
                migrate_bronze(profile)

            with _connected(profile.bronze_store) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 99
                assert connection.execute("PRAGMA journal_mode").fetchone()[0] != "wal"
            assert _tables(profile.bronze_store) == set()

    def test_an_empty_file_with_a_negative_version_is_not_adopted(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            profile.bronze_store.parent.mkdir(parents=True)
            with _connected(profile.bronze_store) as connection:
                connection.execute("PRAGMA user_version = -1")

            with pytest.raises(storage.UnsupportedStoreVersionError):
                migrate_bronze(profile)

            with _connected(profile.bronze_store) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == -1
            assert _tables(profile.bronze_store) == set()

    def test_identity_read_guards_refuse_corrupt_identity_fixtures(self) -> None:
        fixtures = {
            "missing": (),
            "duplicate": (("test", "bronze"), ("test", "bronze")),
            "wrong stage": (("test", "silver"),),
            "wrong profile": (("development", "bronze"),),
        }

        for label, rows in fixtures.items():
            with self.subTest(fixture=label), TemporaryDirectory() as directory:
                profile = make_test_profile(directory)
                profile.bronze_store.parent.mkdir(parents=True)
                with _connected(profile.bronze_store) as connection:
                    connection.execute(
                        "CREATE TABLE store_identity (profile TEXT, stage TEXT)"
                    )
                    connection.executemany(
                        "INSERT INTO store_identity (profile, stage) VALUES (?, ?)",
                        rows,
                    )
                    connection.execute("PRAGMA user_version = 1")

                with pytest.raises(storage.StoreIdentityError):
                    BronzeStore(profile)
                with pytest.raises(storage.StoreIdentityError):
                    migrate_bronze(profile)

    def test_a_failing_statement_rolls_back_and_a_retry_succeeds(self) -> None:
        suffix = (
            "CREATE TABLE marker (x TEXT);\n"
            "INSERT INTO marker (x) VALUES (this is not valid sql);\n"
        )
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            with _patched_resources(suffix), pytest.raises(sqlite3.OperationalError):
                migrate_bronze(profile)

            with _connected(profile.bronze_store) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
            assert _tables(profile.bronze_store) == set()

            migrate_bronze(profile)
            with BronzeStore(profile) as store:
                assert store.get_format_failures("absent") == ()

    def test_a_foreign_key_violation_rolls_back_and_a_retry_succeeds(self) -> None:
        suffix = (
            "INSERT INTO source_records (payload_id, record_ordinal, fields)"
            " VALUES ('missing-payload', 1, '{}');\n"
        )
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            with (
                _patched_resources(suffix),
                pytest.raises(storage.ForeignKeyViolationError),
            ):
                migrate_bronze(profile)

            with _connected(profile.bronze_store) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
            assert _tables(profile.bronze_store) == set()

            migrate_bronze(profile)
            with BronzeStore(profile) as store:
                assert store.get_source_records("missing-payload") == ()

    def test_a_resource_suffix_may_use_ordinary_sql_layout(self) -> None:
        suffix = (
            "CREATE TABLE first (x TEXT); CREATE TABLE second (y TEXT);\n"
            "INSERT INTO first (x) VALUES ('a;b'); -- trailing line comment\n"
            "/* trailing block\n   comment */\n"
        )
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)

            with _patched_resources(suffix):
                migrate_bronze(profile)

            with _connected(profile.bronze_store) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
                assert connection.execute("SELECT x FROM first").fetchall() == [
                    ("a;b",)
                ]
            assert _tables(profile.bronze_store) >= {"first", "second"}


if __name__ == "__main__":
    unittest.main()
