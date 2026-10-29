# Copyright 2026 Therkel
"""A production `budget rebuild` that writes stores writes a backup set after it.

Like `import`, every production write is followed by a set covering what was
written (`operations.md`, *Backup and Restore*). The Git check is the system
boundary, so these tests replace `subprocess.run`.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.backups import BackupWriteError, complete_backup_sets
from budget.gold.store import GoldStore
from tests.cli.commands import rebuild
from tests.cli.imports import clean_checkout
from tests.cli.pipelines import household

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


def _rebuild(profile_file: Path, *options: str) -> tuple[int, str, str]:
    """Run `budget rebuild` in production from a clean checkout."""
    with mock.patch("subprocess.run", side_effect=clean_checkout):
        return rebuild(profile_file, *options)


class ProductionRebuildBackupTests(unittest.TestCase):
    def test_a_rebuild_that_publishes_writes_a_set_and_one_that_does_not_writes_none(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            sets_before = len(complete_backup_sets(built.profile))

            status, stdout, stderr = _rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 1" in stdout
            assert "Backup   backup set" in stdout
            assert len(complete_backup_sets(built.profile)) == sets_before + 1

            status, stdout, stderr = _rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            assert "Backup" not in stdout
            assert len(complete_backup_sets(built.profile)) == sets_before + 1

    def test_a_rebuild_from_silver_writes_a_set(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            sets_before = len(complete_backup_sets(built.profile))

            status, stdout, stderr = _rebuild(built.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            assert "Backup   backup set" in stdout
            assert len(complete_backup_sets(built.profile)) == sets_before + 1

    def test_a_store_no_set_covers_refuses_before_anything_is_written(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            # Gold's legacy extracts, which no set covers yet.
            (built.profile.stores / "gold").mkdir()
            sets_before = len(complete_backup_sets(built.profile))

            status, stdout, stderr = _rebuild(built.profile_file, "--from", "silver")

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "holds gold," in stderr
            with GoldStore(built.profile) as gold:
                assert gold.current() is None
            assert len(complete_backup_sets(built.profile)) == sets_before

    def test_a_set_that_cannot_be_written_is_reported_beside_the_rebuild(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            failure = BackupWriteError("the disk is full")

            with mock.patch("budget.cli.back_up", side_effect=failure):
                status, stdout, stderr = _rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "published publication 1" in stdout
            assert "the stores were rebuilt" in stderr
            assert "the disk is full" in stderr
            assert "`budget backup`" in stderr
            with GoldStore(built.profile) as gold:
                assert gold.current() is not None


if __name__ == "__main__":
    unittest.main()
