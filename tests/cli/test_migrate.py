# Copyright 2026 Therkel
"""`budget migrate`: creating and upgrading a profile's Bronze store.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test.
"""

import io
import sqlite3
import unittest
from contextlib import closing, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget.bronze import BronzeStore, migrate_bronze
from budget.bronze.storage import StoreIdentityError
from budget.cli import main
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.cli.profile_files import write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


def _development(folder: Path) -> Profile:
    """The development profile `write_profile` describes inside `folder`."""
    return Profile(name="development", stores=folder / "stores")


def _migrate(profile_file: Path, *options: str) -> tuple[int, str]:
    """Run `budget migrate` with one profile file; return status and stderr."""
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        status = main(["--profile", str(profile_file), "migrate", *options], environ={})
    return status, stderr.getvalue()


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

            status, _ = _migrate(write_profile(folder), "--stage", "bronze")

            assert status == EXIT_OK
            with BronzeStore(_development(folder)):
                pass


class MigrateRefusalTests(unittest.TestCase):
    def test_production_migration_is_refused_before_anything_is_created(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            status, stderr = _migrate(write_profile(folder, name="production"))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "production" in stderr
            assert not (folder / "stores").exists()

    def test_a_stage_that_is_not_built_yet_is_refused(self) -> None:
        for stage in ("silver", "gold"):
            with self.subTest(stage), TemporaryDirectory() as directory:
                folder = Path(directory)

                status, stderr = _migrate(write_profile(folder), "--stage", stage)

                assert status == EXIT_REFUSED_ENVIRONMENT
                assert stage in stderr
                assert not (folder / "stores").exists()

    def test_a_store_of_another_profile_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            migrate_bronze(make_test_profile(folder))

            status, stderr = _migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "'test'" in stderr
            with BronzeStore(make_test_profile(folder)):
                pass

    def test_a_store_newer_than_this_code_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert _migrate(profile_file)[0] == EXIT_OK
            store = _development(folder).bronze_store
            with closing(sqlite3.connect(store)) as connection:
                connection.execute("PRAGMA user_version = 99")

            status, stderr = _migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "99" in stderr
            assert _user_version(store) == 99

    def test_sqlite_below_the_version_floor_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)

            with mock.patch.object(sqlite3, "sqlite_version_info", (3, 51, 2)):
                status, stderr = _migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "3.51.2" in stderr
            assert not (folder / "stores").exists()


if __name__ == "__main__":
    unittest.main()
