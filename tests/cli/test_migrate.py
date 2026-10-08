# Copyright 2026 Therkel
"""`budget migrate`: creating and upgrading a profile's Bronze and Silver stores.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test.
"""

import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget.bronze import BronzeStore, migrate_bronze
from budget.bronze.storage import (
    ForeignKeyViolationError,
    MigrationResourceError,
    StoreIdentityError,
)
from budget.cli import main
from budget.profiles import test_profile as make_test_profile
from budget.silver import SilverStore, migrate_silver
from tests.bronze.migration_resources import (
    SILVER_MIGRATIONS,
    added_migration,
    patched_resources,
)
from tests.cli.commands import migrate
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4

_ORPHAN_SOURCE_RECORD = (
    "INSERT INTO source_records (payload_id, record_ordinal, fields)"
    " VALUES ('missing-payload', 1, '{}');\n"
)
_INVALID_STATEMENT = "INSERT INTO nowhere (x) VALUES (this is not valid sql);\n"


def _user_version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as connection:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])


class MigrateTests(unittest.TestCase):
    def test_migrate_creates_the_development_bronze_store(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            status = main(["--profile", str(profile_file), "migrate"], environ={})

            assert status == EXIT_OK
            development = development_profile(folder)
            with BronzeStore(development):
                pass
            with pytest.raises(StoreIdentityError):
                BronzeStore(make_test_profile(folder))

    def test_the_bronze_stage_can_be_named(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _ = migrate(write_profile(folder), "--stage", "bronze")

            assert status == EXIT_OK
            with BronzeStore(development_profile(folder)):
                pass

    def test_the_silver_stage_can_be_migrated(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _ = migrate(write_profile(folder), "--stage", "silver")

            assert status == EXIT_OK
            development = development_profile(folder)
            assert development.silver_store.exists()
            with SilverStore(development):
                pass

    def test_migrate_creates_both_stores_when_no_stage_is_named(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, _ = migrate(write_profile(folder))

            assert status == EXIT_OK
            development = development_profile(folder)
            assert development.bronze_store.exists()
            assert development.silver_store.exists()
            with BronzeStore(development), SilverStore(development):
                pass


class MigrateRefusalTests(unittest.TestCase):
    def test_production_migration_is_refused_before_anything_is_created(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, stderr = migrate(write_profile(folder, name="production"))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "production" in stderr
            assert not (folder / "stores").exists()

    def test_a_stage_that_is_not_built_yet_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, stderr = migrate(write_profile(folder), "--stage", "gold")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "gold" in stderr
            assert not (folder / "stores").exists()

    def test_a_store_of_another_profile_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            migrate_bronze(make_test_profile(folder))

            status, stderr = migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "'test'" in stderr
            with BronzeStore(make_test_profile(folder)):
                pass

    def test_a_silver_store_of_another_profile_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            migrate_silver(make_test_profile(folder))

            status, stderr = migrate(write_profile(folder), "--stage", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "'test'" in stderr
            with SilverStore(make_test_profile(folder)):
                pass

    def test_a_store_of_another_stage_is_refused(self) -> None:
        # Each stage's file is replaced by a store the other stage migrated.
        for stage, other in (("bronze", "silver"), ("silver", "bronze")):
            with self.subTest(stage=stage), TemporaryDirectory() as directory:
                folder = Path(directory)
                profile_file = write_profile(folder)
                development = development_profile(folder)
                paths = {
                    "bronze": development.bronze_store,
                    "silver": development.silver_store,
                }
                assert migrate(profile_file, "--stage", other)[0] == EXIT_OK
                paths[other].rename(paths[stage])

                status, stderr = migrate(profile_file, "--stage", stage)

                assert status == EXIT_REFUSED_ENVIRONMENT
                assert f"stage {other!r}" in stderr
                with closing(sqlite3.connect(paths[stage])) as connection:
                    assert connection.execute(
                        "SELECT stage FROM store_identity"
                    ).fetchall() == [(other,)]

    def test_production_silver_is_refused_first_for_want_of_bronze(self) -> None:
        # Starting Silver would be refused too until Bronze has a store, so
        # the advice is the step that works first.
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, stderr = migrate(
                write_profile(folder, name="production"), "--stage", "silver"
            )

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "no Bronze store" in stderr
            assert "budget migrate --stage bronze --new-store" in stderr
            assert "120" not in stderr
            assert not (folder / "stores").exists()
            assert not (folder / "backups").exists()

    def test_a_store_newer_than_this_code_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            store = development_profile(folder).bronze_store
            with closing(sqlite3.connect(store)) as connection:
                connection.execute("PRAGMA user_version = 99")

            status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "99" in stderr
            assert _user_version(store) == 99

    def test_a_silver_store_newer_than_this_code_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file, "--stage", "silver")[0] == EXIT_OK
            store = development_profile(folder).silver_store
            with closing(sqlite3.connect(store)) as connection:
                connection.execute("PRAGMA user_version = 99")

            status, stderr = migrate(profile_file, "--stage", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "99" in stderr
            assert _user_version(store) == 99

    def test_sqlite_below_the_version_floor_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with mock.patch.object(sqlite3, "sqlite_version_info", (3, 51, 2)):
                status, stderr = migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "3.51.2" in stderr
            assert not (folder / "stores").exists()

    def test_a_store_another_program_holds_is_refused(self) -> None:
        # Such as DB Browser for SQLite, left open in a write transaction.
        # The command waits out the real busy timeout, about five seconds.
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            store = development_profile(folder).bronze_store
            store.parent.mkdir(parents=True)
            with closing(sqlite3.connect(store, isolation_level=None)) as holder:
                holder.execute("BEGIN EXCLUSIVE")

                status, stderr = migrate(write_profile(folder))

                holder.execute("ROLLBACK")
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert f"{store} is in use" in stderr
            assert store.read_bytes() == b""


class MigrateDefectTests(unittest.TestCase):
    def test_a_broken_packaged_migration_is_a_defect_not_a_refusal(self) -> None:
        # A defect propagates out of `main`, so Python reports it and exits 1.
        cases = {
            "an incomplete statement": (
                "CREATE TABLE marker (x TEXT)\n",
                MigrationResourceError,
            ),
            "a foreign-key violation": (
                _ORPHAN_SOURCE_RECORD,
                ForeignKeyViolationError,
            ),
        }
        for case, (suffix, defect) in cases.items():
            with (
                self.subTest(case),
                TemporaryDirectory() as directory,
                patched_resources(suffix),
                pytest.raises(defect),
            ):
                migrate(write_profile(Path(directory)))

    def test_a_failed_migration_commits_none_of_the_steps_before_it(self) -> None:
        # The first step would make a store, the added second one fails it.
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with (
                added_migration(_ORPHAN_SOURCE_RECORD),
                pytest.raises(ForeignKeyViolationError),
            ):
                migrate(write_profile(folder))

            store = development_profile(folder).bronze_store
            assert _user_version(store) == 0
            with closing(sqlite3.connect(store)) as connection:
                assert (
                    connection.execute("SELECT * FROM sqlite_master").fetchall() == []
                )

    def test_a_failed_silver_migration_commits_none_of_the_steps_before_it(
        self,
    ) -> None:
        # The first step would make a store, the added second one fails it.
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with (
                added_migration(_INVALID_STATEMENT, folder=SILVER_MIGRATIONS),
                pytest.raises(sqlite3.OperationalError, match='near "sql"'),
            ):
                migrate(write_profile(folder), "--stage", "silver")

            store = development_profile(folder).silver_store
            assert _user_version(store) == 0
            with closing(sqlite3.connect(store)) as connection:
                assert (
                    connection.execute("SELECT * FROM sqlite_master").fetchall() == []
                )


if __name__ == "__main__":
    unittest.main()
