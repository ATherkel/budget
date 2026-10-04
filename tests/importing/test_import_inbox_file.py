# Copyright 2026 Therkel
"""Importing one inbox export: Bronze, the export archive and the import log.

Every test drives `import_inbox_file` on a synthetic household under its
writer lock, then reads the outcome back from the reopened Bronze store, the
export archive, `imports.jsonl` and the inbox.
"""

import os
import unittest
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from budget.bronze import BronzeStore, ImportDeclaration, ImportRun
from budget.importing import (
    ArchiveConflictError,
    Coverage,
    ImportLogAheadOfBronzeError,
    ImportLogDamagedError,
    InboxImport,
    NotAnInboxFileError,
    UnknownInboxAccountError,
    import_inbox_file,
)
from budget.inputs import ConfigurationError, MisfiledExportError
from budget.locking import WriterLockReleasedError, writer_lock
from budget.profiles import Profile, ProfilePathOutsideRootError
from tests.importing.households import drop, household, log_entries, payload

EXPORT = "export-20260502.csv"
APRIL = Coverage(covers_from=date(2026, 4, 1), covers_through=date(2026, 5, 2))
LATER_EXPORT = "export-20260503.csv"
# Right for LATER_EXPORT; for EXPORT it ends after the export date, so Bronze
# refuses it.
THROUGH_MAY_3 = Coverage(covers_from=date(2026, 4, 1), covers_through=date(2026, 5, 3))


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

            with writer_lock(profile) as lock:
                first = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, content), APRIL
                )
                again = import_inbox_file(
                    lock,
                    drop(profile, "joint-current", LATER_EXPORT, content),
                    THROUGH_MAY_3,
                )

            assert again.import_run.outcome == "repeat"
            assert again.import_run.repeat_of == first.import_run.import_run_id
            assert again.archive_path == "joint-current/export-20260503.csv"
            assert (
                profile.exports / "joint-current" / LATER_EXPORT
            ).read_bytes() == content
            entries = log_entries(profile)
            assert [entry["import_run_id"] for entry in entries] == [
                first.import_run.import_run_id,
                again.import_run.import_run_id,
            ]
            assert entries[1]["outcome"] == "repeat"
            assert entries[1]["repeat_of"] == first.import_run.import_run_id
            assert entries[1]["covers_through"] == "2026-05-03"


class ArchiveNameTests(unittest.TestCase):
    def test_a_name_taken_by_other_bytes_is_archived_under_the_hash_folder(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            earlier = payload("01.04.2026")
            corrected = payload("01.04.2026", "02.04.2026")

            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, earlier), APRIL
                )
                result = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, corrected), APRIL
                )

            hash_folder = sha256(corrected).hexdigest()[:12]
            assert result.archive_path == f"joint-current/{hash_folder}/{EXPORT}"
            assert (profile.exports / result.archive_path).read_bytes() == corrected
            assert (profile.exports / "joint-current" / EXPORT).read_bytes() == earlier
            assert log_entries(profile)[1]["archive_path"] == result.archive_path

    def test_an_archived_file_standing_where_a_folder_must_go_is_a_conflict(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            # An export saved under the name the refused copies' folder takes.
            named_refused = Coverage(
                covers_from=date(2026, 4, 1),
                covers_through=date(2026, 5, 2),
                exported_on=date(2026, 5, 2),
            )
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", "refused", payload("01.04.2026")),
                    named_refused,
                )
                source = drop(profile, "joint-current", EXPORT, payload("02.04.2026"))

                with pytest.raises(ArchiveConflictError):
                    import_inbox_file(lock, source, THROUGH_MAY_3)

            assert (profile.exports / "joint-current" / "refused").is_file()
            assert source.exists()

    def test_a_retry_restores_a_lost_copy_where_its_log_entry_says(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            corrected = payload("01.04.2026", "02.04.2026")
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
                first = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, corrected), APRIL
                )
            # Both archived copies go missing, which frees the plain name; then
            # the corrected file turns up in the inbox again.
            (profile.exports / "joint-current" / EXPORT).unlink()
            (profile.exports / first.archive_path).unlink()
            source = drop(profile, "joint-current", EXPORT, corrected)

            with writer_lock(profile) as lock:
                again = import_inbox_file(lock, source, APRIL)

            assert again.archive_path == first.archive_path
            assert (profile.exports / first.archive_path).read_bytes() == corrected
            assert not (profile.exports / "joint-current" / EXPORT).exists()

    def test_a_place_another_runs_entry_names_is_never_taken_by_a_new_run(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            same_day_again = payload("01.04.2026", "02.04.2026")
            with writer_lock(profile) as lock:
                first = import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
            # The first export's archived copy goes missing; its entry still
            # names the plain name, which is therefore not free.
            (profile.exports / first.archive_path).unlink()

            with writer_lock(profile) as lock:
                second = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, same_day_again), APRIL
                )

            hash_folder = sha256(same_day_again).hexdigest()[:12]
            assert second.archive_path == f"joint-current/{hash_folder}/{EXPORT}"
            assert not (profile.exports / first.archive_path).exists()

    def test_an_archived_export_named_like_a_temporary_file_is_never_overwritten(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            first = payload("01.04.2026")
            declared_export_date = Coverage(
                covers_from=date(2026, 4, 1),
                covers_through=date(2026, 5, 2),
                exported_on=date(2026, 5, 2),
            )
            with writer_lock(profile) as lock:
                earlier = import_inbox_file(
                    lock,
                    drop(profile, "joint-current", ".x.csv.partial", first),
                    declared_export_date,
                )
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", "x.csv", payload("02.04.2026")),
                    declared_export_date,
                )

            assert (profile.exports / earlier.archive_path).read_bytes() == first

    def test_a_retry_finds_its_archived_copy_before_a_place_freed_since(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            corrected = payload("01.04.2026", "02.04.2026")
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
                first = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, corrected), APRIL
                )
            # Someone moves the earlier export aside; then the corrected file
            # turns up in the inbox again, as after a crash before its removal.
            (profile.exports / "joint-current" / EXPORT).rename(
                Path(directory) / "aside.csv"
            )
            source = drop(profile, "joint-current", EXPORT, corrected)

            with writer_lock(profile) as lock:
                again = import_inbox_file(lock, source, APRIL)

            assert again.archive_path == first.archive_path
            assert not (profile.exports / "joint-current" / EXPORT).exists()

    def test_an_archive_folder_replaced_by_a_symlink_out_of_the_root_is_refused(
        self,
    ) -> None:
        with TemporaryDirectory() as directory, TemporaryDirectory() as outside:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            profile.exports.mkdir()
            try:
                (profile.exports / "joint-current").symlink_to(
                    Path(outside), target_is_directory=True
                )
            except OSError as error:  # Windows may refuse without a privilege
                self.skipTest(f"symlinks are unavailable here: {error}")

            with (
                writer_lock(profile) as lock,
                pytest.raises(ProfilePathOutsideRootError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert list(Path(outside).iterdir()) == []
            assert source.read_bytes() == content

    def test_conflicting_bytes_in_the_hash_folder_are_never_overwritten(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            account_folder = profile.exports / "joint-current"
            hash_folder = account_folder / sha256(content).hexdigest()[:12]
            hash_folder.mkdir(parents=True)
            (account_folder / EXPORT).write_bytes(b"other bytes")
            (hash_folder / EXPORT).write_bytes(b"yet other bytes")

            with (
                writer_lock(profile) as lock,
                pytest.raises(ArchiveConflictError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert (account_folder / EXPORT).read_bytes() == b"other bytes"
            assert (hash_folder / EXPORT).read_bytes() == b"yet other bytes"
            assert source.read_bytes() == content
            assert not profile.import_log_file.exists()

    def test_an_earlier_run_with_no_free_archive_place_stops_the_next_import_early(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            blocked = payload("01.04.2026")
            record_in_bronze_only(
                profile, drop(profile, "joint-current", EXPORT, blocked), APRIL
            )
            account_folder = profile.exports / "joint-current"
            hash_folder = account_folder / sha256(blocked).hexdigest()[:12]
            hash_folder.mkdir(parents=True)
            (account_folder / EXPORT).write_bytes(b"other bytes")
            (hash_folder / EXPORT).write_bytes(b"yet other bytes")
            content = payload("02.04.2026")
            source = drop(profile, "joint-savings", EXPORT, content)

            with (
                writer_lock(profile) as lock,
                pytest.raises(ArchiveConflictError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert source.read_bytes() == content
            with BronzeStore(profile) as store, pytest.raises(KeyError):
                store.get_payload(sha256(content).hexdigest())
            assert not (profile.exports / "joint-savings").exists()
            assert not profile.import_log_file.exists()


def assert_nothing_written(profile: Profile, source: Path, content: bytes) -> None:
    """The file is still in the inbox, and no store, archive or log has it."""
    assert source.read_bytes() == content
    with BronzeStore(profile) as store, pytest.raises(KeyError):
        store.get_payload(sha256(content).hexdigest())
    assert not profile.exports.exists()
    assert not profile.import_log_file.exists()


class RefusedBeforeBronzeTests(unittest.TestCase):
    def test_a_folder_that_names_no_account_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-checking", EXPORT, content)

            with (
                writer_lock(profile) as lock,
                pytest.raises(UnknownInboxAccountError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert_nothing_written(profile, source, content)

    def test_a_file_outside_an_account_inbox_folder_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            places = {
                "the inbox itself": profile.inbox,
                "a subfolder of an account's folder": profile.inbox
                / "joint-current"
                / "old",
                "the inputs folder": profile.inputs / "joint-current",
            }
            for place, folder in places.items():
                with self.subTest(place):
                    folder.mkdir(parents=True, exist_ok=True)
                    source = folder / EXPORT
                    source.write_bytes(content)

                    with (
                        writer_lock(profile) as lock,
                        pytest.raises(NotAnInboxFileError),
                    ):
                        import_inbox_file(lock, source, APRIL)

                    assert_nothing_written(profile, source, content)

    def test_a_misfiled_export_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            # joint-current declares 0012345678; this name carries another.
            misfiled = "Konto-0099999999-20260502.csv"
            source = drop(profile, "joint-current", misfiled, content)

            with (
                writer_lock(profile) as lock,
                pytest.raises(MisfiledExportError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert_nothing_written(profile, source, content)

    def test_an_accounts_file_with_problems_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            profile.accounts_file.write_text("format = 2\n", encoding="utf-8")
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)

            with (
                writer_lock(profile) as lock,
                pytest.raises(ConfigurationError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert_nothing_written(profile, source, content)


def record_in_bronze_only(
    profile: Profile, source: Path, coverage: Coverage
) -> ImportRun:
    """Leave the state of a crash right after Bronze committed a joint-current run."""
    with BronzeStore(profile) as store:
        return store.import_file(
            source,
            ImportDeclaration(
                declared_account_id="joint-current",
                source_format="danske-csv-v1",
                covers_from=coverage.covers_from,
                covers_through=coverage.covers_through,
            ),
        )


class RetryTests(unittest.TestCase):
    """A rerun after a crash finishes the earlier run instead of adding one.

    Each test builds the state a crash leaves after one step, through public
    interfaces, and puts the file back where the household left it.
    """

    def test_a_run_stored_before_a_crash_is_archived_logged_and_not_repeated(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            # The crash came after Bronze committed, before the archive.
            earlier = record_in_bronze_only(profile, source, APRIL)

            with writer_lock(profile) as lock:
                result = import_inbox_file(lock, source, APRIL)

            assert result.import_run == earlier
            assert (profile.exports / "joint-current" / EXPORT).read_bytes() == content
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                earlier.import_run_id
            ]
            assert not source.exists()

    def test_a_logged_run_whose_file_stayed_in_the_inbox_is_only_finished(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            with writer_lock(profile) as lock:
                first = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, content), APRIL
                )
            # The crash came after the log, before the file left the inbox.
            source = drop(profile, "joint-current", EXPORT, content)

            with writer_lock(profile) as lock:
                again = import_inbox_file(lock, source, APRIL)

            assert again.import_run == first.import_run
            assert again.archive_path == first.archive_path
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                first.import_run.import_run_id
            ]
            assert not source.exists()

    def test_every_run_bronze_holds_is_logged_before_an_import_finishes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            refused_bytes = payload("01.04.2026")
            refused_source = drop(profile, "joint-current", EXPORT, refused_bytes)
            # A refused run's crash came after Bronze committed. Its file stays
            # in the inbox, so no retry of that file would ever finish it.
            interrupted = record_in_bronze_only(profile, refused_source, THROUGH_MAY_3)

            with writer_lock(profile) as lock:
                result = import_inbox_file(
                    lock,
                    drop(profile, "joint-savings", EXPORT, payload("02.04.2026")),
                    APRIL,
                )

            refused_copy = (
                f"joint-current/refused/{sha256(refused_bytes).hexdigest()[:12]}/"
                f"{EXPORT}"
            )
            assert interrupted.outcome == "refused"
            assert (profile.exports / refused_copy).read_bytes() == refused_bytes
            entries = log_entries(profile)
            assert [entry["import_run_id"] for entry in entries] == [
                interrupted.import_run_id,
                result.import_run.import_run_id,
            ]
            assert entries[0]["archive_path"] == refused_copy
            assert refused_source.read_bytes() == refused_bytes

    def test_a_repeat_run_stored_before_a_crash_is_finished_not_repeated(
        self,
    ) -> None:
        # A guard: the retry identity covers repeat runs as well as stored ones.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            with writer_lock(profile) as lock:
                first = import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, content), APRIL
                )
            source = drop(profile, "joint-current", LATER_EXPORT, content)
            interrupted = record_in_bronze_only(profile, source, THROUGH_MAY_3)

            with writer_lock(profile) as lock:
                result = import_inbox_file(lock, source, THROUGH_MAY_3)

            assert interrupted.outcome == "repeat"
            assert result.import_run == interrupted
            with BronzeStore(profile) as store:
                assert len(store.import_runs()) == 2
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                first.import_run.import_run_id,
                interrupted.import_run_id,
            ]
            assert not source.exists()

    def test_the_same_file_in_another_account_is_refused_not_finished(
        self,
    ) -> None:
        # A guard: the account is part of the retry identity, so the bytes a
        # first account stored are an account conflict in a second one.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock, drop(profile, "joint-current", EXPORT, content), APRIL
                )
                source = drop(profile, "joint-savings", EXPORT, content)
                result = import_inbox_file(lock, source, APRIL)

            assert result.import_run.outcome == "refused"
            assert result.import_run.declared_account_id == "joint-savings"
            assert result.left_in_inbox
            assert source.read_bytes() == content

    def test_a_refused_run_is_not_finished_by_a_corrected_rerun(self) -> None:
        # A guard: a corrected declaration is a new presentation, never a retry.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)

            with writer_lock(profile) as lock:
                refused = import_inbox_file(lock, source, THROUGH_MAY_3)
                corrected = import_inbox_file(lock, source, APRIL)

            assert corrected.import_run.outcome == "stored"
            assert (
                corrected.import_run.import_run_id != refused.import_run.import_run_id
            )
            assert [entry["outcome"] for entry in log_entries(profile)] == [
                "refused",
                "stored",
            ]
            assert not source.exists()


class CutOffLogTests(unittest.TestCase):
    """A crash while an entry is appended leaves it without its line feed."""

    def test_an_entry_cut_off_by_a_crash_is_completed_from_its_run(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            second = payload("02.04.2026")
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", LATER_EXPORT, second),
                    THROUGH_MAY_3,
                )
            complete = profile.import_log_file.read_bytes()
            first_entry_end = complete.index(b"\n") + 1
            cut_off = first_entry_end + (len(complete) - first_entry_end) // 2
            profile.import_log_file.write_bytes(complete[:cut_off])
            source = drop(profile, "joint-current", LATER_EXPORT, second)

            with writer_lock(profile) as lock:
                import_inbox_file(lock, source, THROUGH_MAY_3)

            assert profile.import_log_file.read_bytes() == complete
            assert not source.exists()

    def test_a_cut_off_entry_no_run_accounts_for_is_refused_before_writing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
            damaged = profile.import_log_file.read_bytes() + (
                b'{"format": 1, "import_run_id": "no-such-run"'
            )
            profile.import_log_file.write_bytes(damaged)
            content = payload("02.04.2026")
            source = drop(profile, "joint-savings", EXPORT, content)

            with (
                writer_lock(profile) as lock,
                pytest.raises(ImportLogDamagedError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert profile.import_log_file.read_bytes() == damaged
            assert source.read_bytes() == content
            with BronzeStore(profile) as store, pytest.raises(KeyError):
                store.get_payload(sha256(content).hexdigest())
            assert not (profile.exports / "joint-savings").exists()


class InjectedCrashError(Exception):
    """Stands in for the process dying at one file step."""


@contextmanager
def crash_at(step: int) -> Iterator[None]:
    """Fail the `step`-th file step: an fsync, a rename or an unlink.

    These are the system calls that make an import's file work durable or
    final, so failing each in turn leaves every state a crash can.
    """
    calls = 0

    def failing(original: Callable[..., object]) -> Callable[..., object]:
        def step_or_crash(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            if calls == step:
                raise InjectedCrashError
            return original(*args, **kwargs)

        return step_or_crash

    with (
        patch("os.fsync", failing(os.fsync)),
        patch.object(Path, "rename", failing(Path.rename)),
        patch.object(Path, "unlink", failing(Path.unlink)),
    ):
        yield


def import_with_crash_at(
    profile: Profile, source: Path, coverage: Coverage, step: int
) -> tuple[InboxImport, bool]:
    """Import with a crash at one step, then rerun without it if it crashed.

    Returns the import that finished, and whether the crash happened.
    """
    with writer_lock(profile) as lock:
        try:
            with crash_at(step):
                return import_inbox_file(lock, source, coverage), False
        except InjectedCrashError:
            return import_inbox_file(lock, source, coverage), True


CRASHED_CONTENT = payload("01.04.2026")
# More file steps than an import has, so a defect cannot loop forever.
MOST_FILE_STEPS = 20


class InjectedCrashTests(unittest.TestCase):
    """Guards: the retry tests built each crash state by hand; these reach them
    by failing each file step of a real import in turn, then rerunning.
    """

    def _crash_at_every_step(
        self,
        coverage: Coverage,
        check: Callable[[Profile, Path, InboxImport], None],
    ) -> int:
        """Crash at step 1, 2, … until an import crashes nowhere; check each.

        Returns the number of passes, the last of which did not crash.
        """
        step = 0
        crashed = True
        while crashed and step < MOST_FILE_STEPS:
            step += 1
            with self.subTest(step=step), TemporaryDirectory() as directory:
                profile = household(Path(directory))
                source = drop(profile, "joint-current", EXPORT, CRASHED_CONTENT)
                result, crashed = import_with_crash_at(profile, source, coverage, step)
                check(profile, source, result)
        return step

    def test_a_crash_at_any_file_step_is_finished_by_a_rerun(self) -> None:
        def finished_once(profile: Profile, source: Path, result: InboxImport) -> None:
            with BronzeStore(profile) as store:
                assert store.import_runs() == (result.import_run,)
            assert result.import_run.outcome == "stored"
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                result.import_run.import_run_id
            ]
            archived = profile.exports / result.archive_path
            assert archived.read_bytes() == CRASHED_CONTENT
            assert not source.exists()

        passes = self._crash_at_every_step(APRIL, finished_once)

        # The archive's fsync and rename, the log's fsync, and the unlink.
        assert passes > 4

    def test_a_crash_while_refusing_leaves_every_refused_run_logged(self) -> None:
        def every_run_logged(
            profile: Profile, source: Path, result: InboxImport
        ) -> None:
            # A refused run is never retried, so a rerun after a crash adds
            # its own refused run; both must reach the log, in Bronze's order.
            with BronzeStore(profile) as store:
                runs = store.import_runs()
            assert result.import_run in runs
            assert {run.outcome for run in runs} == {"refused"}
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                run.import_run_id for run in runs
            ]
            archived = profile.exports / result.archive_path
            assert archived.read_bytes() == CRASHED_CONTENT
            assert source.read_bytes() == CRASHED_CONTENT

        passes = self._crash_at_every_step(THROUGH_MAY_3, every_run_logged)

        # The refused copy's fsync and rename, and the log's fsync.
        assert passes > 3


class ChangedSourceTests(unittest.TestCase):
    def test_a_file_saved_over_during_its_import_stays_in_the_inbox(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            replacement = payload("01.04.2026", "02.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            real_fsync = os.fsync

            def fsync_then_save_over(descriptor: int) -> None:
                # The household saves a new download over the file mid-import.
                real_fsync(descriptor)
                source.write_bytes(replacement)

            with (
                writer_lock(profile) as lock,
                patch("os.fsync", fsync_then_save_over),
            ):
                result = import_inbox_file(lock, source, APRIL)

            assert result.import_run.payload_id == sha256(content).hexdigest()
            assert (profile.exports / result.archive_path).read_bytes() == content
            assert result.left_in_inbox
            assert source.read_bytes() == replacement


class RemovedSourceTests(unittest.TestCase):
    def test_a_file_removed_during_its_import_still_finishes_the_import(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            real_fsync = os.fsync

            def fsync_then_remove(descriptor: int) -> None:
                # The household deletes the file from the inbox mid-import.
                real_fsync(descriptor)
                source.unlink(missing_ok=True)

            with (
                writer_lock(profile) as lock,
                patch("os.fsync", fsync_then_remove),
            ):
                result = import_inbox_file(lock, source, APRIL)

            assert result.import_run.outcome == "stored"
            assert not result.left_in_inbox
            assert (profile.exports / result.archive_path).read_bytes() == content
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                result.import_run.import_run_id
            ]

    def test_a_refused_file_removed_during_its_import_is_not_reported_left(
        self,
    ) -> None:
        # A guard: `left_in_inbox` says where the file is, refused or not.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            source = drop(profile, "joint-current", EXPORT, payload("01.04.2026"))
            real_fsync = os.fsync

            def fsync_then_remove(descriptor: int) -> None:
                real_fsync(descriptor)
                source.unlink(missing_ok=True)

            with (
                writer_lock(profile) as lock,
                patch("os.fsync", fsync_then_remove),
            ):
                result = import_inbox_file(lock, source, THROUGH_MAY_3)

            assert result.import_run.outcome == "refused"
            assert not result.left_in_inbox


class FailedWriteTests(unittest.TestCase):
    def test_a_failed_archive_write_leaves_no_temporary_file(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            source = drop(profile, "joint-current", EXPORT, payload("01.04.2026"))
            disk_full = OSError(28, "No space left on device")

            with (
                writer_lock(profile) as lock,
                patch("os.fsync", side_effect=disk_full),
                pytest.raises(OSError, match="No space left"),
            ):
                import_inbox_file(lock, source, APRIL)

            assert list(profile.exports.rglob("*.partial")) == []
            assert source.exists()


class LockedSourceTests(unittest.TestCase):
    def test_a_file_another_program_holds_is_left_in_the_inbox(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)

            def held_by_another_program(path: Path, **_: object) -> None:
                # Windows refuses to delete a file a spreadsheet has open.
                raise PermissionError(13, "the file is in use", str(path))

            with (
                writer_lock(profile) as lock,
                patch.object(Path, "unlink", held_by_another_program),
            ):
                result = import_inbox_file(lock, source, APRIL)

            assert result.import_run.outcome == "stored"
            assert result.left_in_inbox
            assert source.read_bytes() == content
            assert [entry["import_run_id"] for entry in log_entries(profile)] == [
                result.import_run.import_run_id
            ]


class WriterLockTests(unittest.TestCase):
    def test_a_released_lock_is_refused_before_writing(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            with writer_lock(profile) as lock:
                pass

            with pytest.raises(WriterLockReleasedError):
                import_inbox_file(lock, source, APRIL)

            assert_nothing_written(profile, source, content)


class CutOffProofTests(unittest.TestCase):
    def test_a_cut_off_entry_is_never_completed_from_a_run_not_yet_archived(
        self,
    ) -> None:
        # A guard: an entry is written only after its run is archived, so an
        # unarchived run cannot be the one a cut-off entry began.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            record_in_bronze_only(
                profile,
                drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                APRIL,
            )
            profile.import_log_file.write_bytes(b"{")
            content = payload("02.04.2026")
            source = drop(profile, "joint-savings", EXPORT, content)

            with (
                writer_lock(profile) as lock,
                pytest.raises(ImportLogDamagedError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert profile.import_log_file.read_bytes() == b"{"
            assert source.read_bytes() == content
            assert not profile.exports.exists()

    def test_a_cut_off_entry_is_never_completed_from_a_run_already_logged(
        self,
    ) -> None:
        # A guard: this cut-off begins every entry, the logged run's included.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
                import_inbox_file(
                    lock,
                    drop(profile, "joint-savings", EXPORT, payload("02.04.2026")),
                    APRIL,
                )
            complete = profile.import_log_file.read_bytes()
            first_entry = complete[: complete.index(b"\n") + 1]
            shared_start = b'{"format": 1, "import_run_id": "'
            assert complete[len(first_entry) :].startswith(shared_start)
            profile.import_log_file.write_bytes(first_entry + shared_start)

            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", LATER_EXPORT, payload("03.04.2026")),
                    THROUGH_MAY_3,
                )

            assert profile.import_log_file.read_bytes().startswith(complete)
            assert len(log_entries(profile)) == 3


class DamagedLogTests(unittest.TestCase):
    def test_an_archive_path_no_run_could_have_is_refused_before_writing(
        self,
    ) -> None:
        archived_at = b'"archive_path": "joint-current/export-20260502.csv"'
        edits = {
            "a path out of the archive": b'"archive_path": "../../elsewhere.csv"',
            # A guard: a path that is not text never matched its run.
            "a path that is not text": b'"archive_path": 123',
        }
        for edit, replacement in edits.items():
            with self.subTest(edit), TemporaryDirectory() as directory:
                profile = household(Path(directory))
                with writer_lock(profile) as lock:
                    import_inbox_file(
                        lock,
                        drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                        APRIL,
                    )
                log = profile.import_log_file.read_bytes()
                assert archived_at in log
                profile.import_log_file.write_bytes(
                    log.replace(archived_at, replacement)
                )
                source = drop(profile, "joint-savings", EXPORT, payload("02.04.2026"))

                with (
                    writer_lock(profile) as lock,
                    pytest.raises(ImportLogDamagedError),
                ):
                    import_inbox_file(lock, source, APRIL)

    def test_an_entry_must_restate_its_run_exactly(self) -> None:
        # JSON `true` equals Python's 1, so only an exact comparison sees it.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
            log = profile.import_log_file.read_bytes()
            assert log.startswith(b'{"format": 1,')
            profile.import_log_file.write_bytes(
                log.replace(b'{"format": 1,', b'{"format": true,', 1)
            )
            source = drop(profile, "joint-savings", EXPORT, payload("02.04.2026"))

            with (
                writer_lock(profile) as lock,
                pytest.raises(ImportLogDamagedError),
            ):
                import_inbox_file(lock, source, APRIL)

    def test_a_log_ahead_of_bronze_is_told_apart_from_a_damaged_one(self) -> None:
        # Rolling the log back would lose the runs Bronze lacks; Bronze must be
        # brought up to the log instead, so the refusal says which case it is.
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            profile.import_log_file.write_bytes(
                b'{"format": 1, "import_run_id": "run-bronze-never-saw"}\n'
            )
            source = drop(profile, "joint-current", EXPORT, payload("01.04.2026"))

            with (
                writer_lock(profile) as lock,
                pytest.raises(ImportLogAheadOfBronzeError) as refusal,
            ):
                import_inbox_file(lock, source, APRIL)

            # Never caught as damage, whose remedy is to roll the log back.
            assert not isinstance(refusal.value, ImportLogDamagedError)
            assert source.exists()

    def test_an_entry_that_disagrees_with_its_run_is_refused_before_writing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                    APRIL,
                )
            log = profile.import_log_file.read_bytes()
            edited = log.replace(
                b'"covers_through": "2026-05-02"', b'"covers_through": "2026-05-09"'
            )
            assert edited != log
            profile.import_log_file.write_bytes(edited)
            content = payload("02.04.2026")
            source = drop(profile, "joint-savings", EXPORT, content)

            with (
                writer_lock(profile) as lock,
                pytest.raises(ImportLogDamagedError),
            ):
                import_inbox_file(lock, source, APRIL)

            assert profile.import_log_file.read_bytes() == edited
            assert source.read_bytes() == content

    def test_a_log_line_no_run_accounts_for_is_refused_before_writing(self) -> None:
        damages: dict[str, Callable[[bytes], bytes]] = {
            "a blank line": lambda _: b"\n",
            "a line that is not JSON": lambda _: b"not an entry\n",
            "an entry that names no run": lambda _: b'{"format": 1}\n',
            # A guard: added with the check that every line is a run's entry.
            "a second entry for one run": lambda log: log,
        }
        for problem, damage_to in damages.items():
            with self.subTest(problem), TemporaryDirectory() as directory:
                profile = household(Path(directory))
                with writer_lock(profile) as lock:
                    import_inbox_file(
                        lock,
                        drop(profile, "joint-current", EXPORT, payload("01.04.2026")),
                        APRIL,
                    )
                log = profile.import_log_file.read_bytes()
                damaged = log + damage_to(log)
                profile.import_log_file.write_bytes(damaged)
                content = payload("02.04.2026")
                source = drop(profile, "joint-savings", EXPORT, content)

                with (
                    writer_lock(profile) as lock,
                    pytest.raises(ImportLogDamagedError),
                ):
                    import_inbox_file(lock, source, APRIL)

                assert profile.import_log_file.read_bytes() == damaged
                assert source.read_bytes() == content
                with BronzeStore(profile) as store, pytest.raises(KeyError):
                    store.get_payload(sha256(content).hexdigest())


class RefusedImportTests(unittest.TestCase):
    def test_a_refused_run_is_logged_with_a_refused_copy_and_stays_in_the_inbox(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026")
            source = drop(profile, "joint-current", EXPORT, content)
            # The declared range ends after the export date, so Bronze refuses.

            with writer_lock(profile) as lock:
                result = import_inbox_file(lock, source, THROUGH_MAY_3)

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
