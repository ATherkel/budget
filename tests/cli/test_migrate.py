# Copyright 2026 Therkel
"""`budget migrate`: creating and upgrading a profile's Bronze store.

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
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.bronze.migration_resources import patched_resources
from tests.cli.commands import migrate
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4

_ORPHAN_SOURCE_RECORD = (
    "INSERT INTO source_records (payload_id, record_ordinal, fields)"
    " VALUES ('missing-payload', 1, '{}');\n"
)


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
            development = Profile(name="development", stores=folder / "stores")
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
        for stage in ("silver", "gold"):
            with self.subTest(stage), TemporaryDirectory() as directory:
                folder = Path(directory)

                status, stderr = migrate(write_profile(folder), "--stage", stage)

                assert status == EXIT_REFUSED_ENVIRONMENT
                assert stage in stderr
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

    def test_sqlite_below_the_version_floor_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with mock.patch.object(sqlite3, "sqlite_version_info", (3, 51, 2)):
                status, stderr = migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "3.51.2" in stderr
            assert not (folder / "stores").exists()


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


if __name__ == "__main__":
    unittest.main()
