# Copyright 2026 Therkel
"""Migrating production: what is said when the backup after a migration fails.

Each production profile here is a synthetic profile file in a temporary
folder; no test opens a real production store.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

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


if __name__ == "__main__":
    unittest.main()
