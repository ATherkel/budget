# Copyright 2026 Therkel
"""Migrating production: what is said when the backup after a migration fails.

Each production profile here is a synthetic profile file in a temporary
folder; no test opens a real production store.
"""

import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget.backups import complete_backup_sets
from budget.locking import writer_lock
from budget.migration import MigratedWithoutBackupError, migrate_profile
from budget.profiles import load_profile_file
from tests.backups.sets import NOW, user_version
from tests.bronze.migration_resources import added_migration
from tests.cli.commands import migrate
from tests.cli.profile_files import write_profile

EXIT_OK = 0
REAL_CONNECT = sqlite3.connect


class MigratedWithoutBackupTests(unittest.TestCase):
    def test_a_backup_that_fails_after_a_migration_says_the_store_was_migrated(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile_file = write_profile(Path(directory), name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)

            with added_migration("CREATE TABLE marker (x TEXT) STRICT;\n"):
                # A clock that stands still names both sets alike, and a set
                # never replaces another: the second one cannot be written.
                with (
                    writer_lock(production) as lock,
                    pytest.raises(MigratedWithoutBackupError, match="budget backup"),
                ):
                    migrate_profile(lock, clock=lambda: NOW)

                assert user_version(production.bronze_store) == 2
                sets = complete_backup_sets(production)
            # The new store's own set, and the one taken before the migration.
            assert len(sets) == 2
            assert NOW in {written.created_at for written in sets}

    def test_a_snapshot_sqlite_cannot_write_after_a_migration_says_so_too(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder, name="production")
            assert migrate(profile_file, "--new-store")[0] == EXIT_OK
            production = load_profile_file(profile_file)
            # The clock names the set before the migration, then the one
            # after it. SQLite cannot open the second set's snapshot in
            # staging, as when the disk is full: an error of SQLite's, not an
            # `OSError`.
            times = iter((NOW, NOW + timedelta(seconds=1)))
            named: list[datetime] = []

            def clock() -> datetime:
                time = next(times)
                named.append(time)
                return time

            def connect(target: str | Path, *, uri: bool = False) -> sqlite3.Connection:
                if len(named) == 2 and "backup-staging" in str(target):
                    missing = folder / "never-written.db"
                    return REAL_CONNECT(f"{missing.as_uri()}?mode=ro", uri=True)
                return REAL_CONNECT(target, uri=uri)

            with added_migration("CREATE TABLE marker (x TEXT) STRICT;\n"):
                with (
                    writer_lock(production) as lock,
                    mock.patch.object(sqlite3, "connect", side_effect=connect),
                    pytest.raises(MigratedWithoutBackupError, match="budget backup"),
                ):
                    migrate_profile(lock, clock=clock)

                assert user_version(production.bronze_store) == 2
                assert list(production.backup_staging.iterdir()) == []


if __name__ == "__main__":
    unittest.main()
