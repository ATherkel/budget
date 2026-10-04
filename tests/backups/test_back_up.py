# Copyright 2026 Therkel
"""Backup sets: a complete, checked copy of a profile, written whole or not at all.

Every profile here is a synthetic test profile in a temporary folder; no test
opens a production store or reads a real export.
"""

import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.backups import back_up, complete_backup_sets
from budget.locking import writer_lock
from tests.backups.sets import (
    NOW,
    checksum,
    copied_run_ids,
    holding,
    import_one,
    manifest,
    run_ids,
)
from tests.importing.households import household


class BackUpTests(unittest.TestCase):
    def test_a_set_holds_a_snapshot_of_bronze_taken_through_the_backup_api(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile = household(folder / "household")
            with closing(holding(profile)), writer_lock(profile) as lock:
                run_id = import_one(lock)
                # The run is still in the WAL file: a copy of the store file
                # alone would miss it.
                assert copied_run_ids(profile.bronze_store, folder) == []

                backup = back_up(lock, now=NOW)

            assert backup.name == "2026-05-02T18-05-11.120731Z"
            assert backup.path == (folder / "household" / "backups" / backup.name)
            assert backup.created_at == NOW
            store = backup.path / "bronze.db"
            written = manifest(backup.path)
            files = written["files"]
            assert isinstance(files, dict)
            assert files["bronze.db"] == checksum(store)
            assert run_ids(store) == [run_id]
            assert written["format"] == 1
            assert written["profile"] == "test"
            assert written["created_at"] == "2026-05-02T18:05:11.120731+00:00"
            assert written["stores"] == {
                "bronze": {"path": "bronze.db", "schema_version": 1}
            }
            assert complete_backup_sets(profile) == (backup,)


if __name__ == "__main__":
    unittest.main()
