# Copyright 2026 Therkel
"""A production `budget rebuild` that writes stores writes a backup set after it.

Like `import`, every production write is followed by a set covering what was
written (`operations.md`, *Backup and Restore*). The Git check is the system
boundary, so these tests replace `subprocess.run`.
"""

import contextlib
import errno
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.backups import BackupWriteError, complete_backup_sets
from budget.gold.store import GoldStore
from tests.cli.commands import rebuild, undo
from tests.cli.imports import clean_checkout
from tests.cli.pipelines import Household, household

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


def _rebuild(profile_file: Path, *options: str) -> tuple[int, str, str]:
    """Run `budget rebuild` in production from a clean checkout."""
    with mock.patch("subprocess.run", side_effect=clean_checkout):
        return rebuild(profile_file, *options)


def _change_gold(built: Household, statement: str) -> None:
    """Change the Gold store behind the application's back."""
    store = next(built.profile.stores.rglob("gold.db"))
    with contextlib.closing(sqlite3.connect(store)) as connection, connection:
        connection.execute(statement)


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

    def test_a_build_after_a_lost_current_result_says_so_and_writes_a_set(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            assert _rebuild(built.profile_file)[0] == EXIT_OK
            # A Gold migration that cannot convert the current result leaves
            # the pointer naming a publication whose result is gone.
            _change_gold(built, "DELETE FROM results WHERE publication_id = 1")
            with built.profile_file.open("a", encoding="utf-8") as profile_file:
                profile_file.write("\n[gold]\nlate_booking_days = 14\n")
            sets_before = len(complete_backup_sets(built.profile))

            status, stdout, stderr = _rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            assert (
                "Changes  publication 1 is no longer retained, so nothing can be "
                "compared; publication 2 is current."
            ) in stdout
            assert "Backup   backup set" in stdout
            assert len(complete_backup_sets(built.profile)) == sets_before + 1

    def test_a_diff_that_fails_still_leaves_a_set_behind_the_publication(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            assert _rebuild(built.profile_file)[0] == EXIT_OK
            _change_gold(
                built,
                "UPDATE transactions SET transaction_date = '2026-13-45' "
                "WHERE publication_id = 1",
            )
            with built.profile_file.open("a", encoding="utf-8") as profile_file:
                profile_file.write("\n[gold]\nlate_booking_days = 14\n")
            sets_before = len(complete_backup_sets(built.profile))

            with self.assertRaises(ValueError):
                _rebuild(built.profile_file)

            assert len(complete_backup_sets(built.profile)) == sets_before + 1

    def test_undo_writes_a_backup_set_after_restoring_the_pointer(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            assert _rebuild(built.profile_file)[0] == EXIT_OK
            with built.profile_file.open("a", encoding="utf-8") as profile_file:
                profile_file.write("\n[gold]\nlate_booking_days = 14\n")
            assert _rebuild(built.profile_file)[0] == EXIT_OK
            sets_before = len(complete_backup_sets(built.profile))

            status, stdout, stderr = undo(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "publication 1 is current (was 2; cause undo)" in stdout
            assert "Backup   backup set" in stdout
            assert len(complete_backup_sets(built.profile)) == sets_before + 1
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1

    def test_an_undo_whose_backup_fails_reports_the_restored_pointer(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")
            assert _rebuild(built.profile_file)[0] == EXIT_OK
            with built.profile_file.open("a", encoding="utf-8") as profile_file:
                profile_file.write("\n[gold]\nlate_booking_days = 14\n")
            assert _rebuild(built.profile_file)[0] == EXIT_OK
            failure = OSError(errno.ENOSPC, "No space left on device")

            with mock.patch("budget.backups.os.fsync", side_effect=failure):
                status, stdout, stderr = undo(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "publication 1 is current (was 2; cause undo)" in stdout
            assert "the current publication was restored" in stderr
            assert "No space left on device" in stderr
            with GoldStore(built.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 1


if __name__ == "__main__":
    unittest.main()
