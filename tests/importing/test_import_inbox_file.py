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

    # Guards rather than red tests: a format failure is a `stored` run and a
    # repeat is accepted like one, so both passed as soon as stored runs did.
    def test_a_format_failure_is_archived_and_logged_like_any_stored_run(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = b'"Date","Text"\r\n"2026-04-01","not this bank"'
            source = drop(profile, "joint-current", EXPORT, content)

            with writer_lock(profile) as lock:
                result = import_inbox_file(lock, source, APRIL)

            run = result.import_run
            assert run.outcome == "stored"
            with BronzeStore(profile) as store:
                assert len(store.get_format_failures(run.payload_id)) == 1
                assert store.get_source_records(run.payload_id) == ()
            assert (profile.exports / "joint-current" / EXPORT).read_bytes() == content
            assert [entry["outcome"] for entry in log_entries(profile)] == ["stored"]
            assert not result.left_in_inbox
            assert not source.exists()

    def test_the_same_bytes_in_a_later_export_are_a_new_repeat_run(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            later = "export-20260503.csv"
            through_may_3 = Coverage(
                covers_from=date(2026, 4, 1), covers_through=date(2026, 5, 3)
            )

            with writer_lock(profile) as lock:
                first = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, content), APRIL
                )
                again = import_inbox_file(
                    lock, drop(profile, "joint-current", later, content), through_may_3
                )

            assert again.import_run.outcome == "repeat"
            assert again.import_run.repeat_of == first.import_run.import_run_id
            assert again.archive_path == "joint-current/export-20260503.csv"
            assert (profile.exports / "joint-current" / later).read_bytes() == content
            entries = log_entries(profile)
            assert [entry["import_run_id"] for entry in entries] == [
                first.import_run.import_run_id,
                again.import_run.import_run_id,
            ]
            assert entries[1]["outcome"] == "repeat"
            assert entries[1]["repeat_of"] == first.import_run.import_run_id
            assert entries[1]["covers_through"] == "2026-05-03"


class RefusedImportTests(unittest.TestCase):
    def test_a_refused_run_is_logged_with_a_refused_copy_and_stays_in_the_inbox(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            # The declared range ends after the export date, so Bronze refuses.
            past_the_export = Coverage(
                covers_from=date(2026, 4, 1), covers_through=date(2026, 5, 3)
            )

            with writer_lock(profile) as lock:
                result = import_inbox_file(lock, source, past_the_export)

            refused_copy = (
                f"joint-current/refused/{sha256(content).hexdigest()[:12]}/{EXPORT}"
            )
            assert result.import_run.outcome == "refused"
            assert result.left_in_inbox
            assert source.read_bytes() == content
            assert result.archive_path == refused_copy
            assert (profile.exports / refused_copy).read_bytes() == content
            assert not (profile.exports / "joint-current" / EXPORT).exists()
            [entry] = log_entries(profile)
            assert entry["import_run_id"] == result.import_run.import_run_id
            assert entry["outcome"] == "refused"
            assert entry["archive_path"] == refused_copy
            assert entry["covers_through"] == "2026-05-03"


if __name__ == "__main__":
    unittest.main()
