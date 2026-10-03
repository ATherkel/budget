# Copyright 2026 Therkel
"""Importing one inbox export: Bronze, the export archive and the import log.

Every test drives `import_inbox_file` on a synthetic household under its
writer lock, then reads the outcome back from the reopened Bronze store, the
export archive, `imports.jsonl` and the inbox.
"""

import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import BronzeStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from tests.importing.households import drop, household, log_entries, payload

APRIL = Coverage(covers_from=date(2026, 4, 1), covers_through=date(2026, 5, 2))
EXPORT = "export-20260502.csv"


class OrdinaryImportTests(unittest.TestCase):
    def test_an_export_is_stored_archived_logged_and_leaves_the_inbox(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026", "30.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)

            with writer_lock(profile) as lock:
                result = import_inbox_file(lock, source, APRIL)

            run = result.import_run
            assert run.outcome == "stored"
            assert run.declared_account_id == "joint-current"
            assert run.source_format == "danske-csv-v1"
            assert run.original_filename == EXPORT
            assert run.exported_on == date(2026, 5, 2)
            assert (run.covers_from, run.covers_through) == (
                date(2026, 4, 1),
                date(2026, 5, 2),
            )
            assert result.archive_path == "joint-current/export-20260502.csv"
            assert not result.left_in_inbox
            assert not source.exists()
            assert (profile.exports / "joint-current" / EXPORT).read_bytes() == content
            with BronzeStore(profile) as store:
                assert store.get_import_run(run.import_run_id) == run
                assert store.get_payload(run.payload_id).content == content
            assert log_entries(profile) == [
                {
                    "format": 1,
                    "import_run_id": run.import_run_id,
                    "account_id": "joint-current",
                    "source_format": "danske-csv-v1",
                    "archive_path": "joint-current/export-20260502.csv",
                    "payload_sha256": sha256(content).hexdigest(),
                    "exported_on": "2026-05-02",
                    "exported_on_source": "filename",
                    "covers_from": "2026-04-01",
                    "covers_through": "2026-05-02",
                    "started_at": run.started_at.isoformat(),
                    "outcome": "stored",
                    "repeat_of": None,
                }
            ]

    def test_one_held_lock_covers_every_file_of_the_inbox(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            current = drop(profile, "joint-current", EXPORT, payload("01.04.2026"))
            savings = drop(profile, "joint-savings", EXPORT, payload("02.04.2026"))

            with writer_lock(profile) as lock:
                first = import_inbox_file(lock, current, APRIL)
                second = import_inbox_file(lock, savings, APRIL)

            assert [first.import_run.outcome, second.import_run.outcome] == [
                "stored",
                "stored",
            ]
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                first.import_run.import_run_id,
                second.import_run.import_run_id,
            ]
            assert not current.exists()
            assert not savings.exists()


if __name__ == "__main__":
    unittest.main()
