# Copyright 2026 Therkel
"""Replaying `imports.jsonl` into Bronze from the export archive.

Every test writes a synthetic archive and import log by hand into a migrated,
empty test profile, replays them under the writer lock, and reads the restored
history back through the reopened Bronze store. The expected runs are written
out independently of the code that writes the log.
"""

import json
import shutil
import unittest
from collections.abc import Callable
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.bronze import BronzeStore, ImportRun
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.replaying import (
    ArchivedExportMismatchError,
    ArchivedExportMissingError,
    ImportLogInvalidError,
    NotALogPrefixError,
    RunConflictError,
    UnknownRepeatOfError,
    replay_import_log,
)
from tests.importing.households import drop, household, payload

STARTED_AT = datetime(2026, 5, 2, 18, 3, 44, 120731, tzinfo=UTC)
LATER = datetime(2026, 5, 3, 9, 0, 0, 5, tzinfo=UTC)
LATEST = datetime(2026, 5, 4, 9, 0, tzinfo=UTC)
LAST = datetime(2026, 5, 5, 9, 0, tzinfo=UTC)


def archive(profile: Profile, archive_path: str, content: bytes) -> str:
    """Put an export into the archive; return its payload hash."""
    target = profile.exports / archive_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return sha256(content).hexdigest()


def entry(
    import_run_id: str, archive_path: str, payload_sha256: str, **changes: object
) -> dict[str, object]:
    """One import-log entry for a stored `joint-current` export of 2 May 2026.

    `changes` replaces any other field of the entry by name.
    """
    return {
        "format": 1,
        "import_run_id": import_run_id,
        "account_id": "joint-current",
        "source_format": "danske-csv-v1",
        "archive_path": archive_path,
        "payload_sha256": payload_sha256,
        "exported_on": "2026-05-02",
        "exported_on_source": "filename",
        "covers_from": "2026-04-01",
        "covers_through": "2026-05-02",
        "started_at": STARTED_AT.isoformat(),
        "outcome": "stored",
        "repeat_of": None,
    } | changes


def line(each: dict[str, object]) -> bytes:
    """One complete import-log line holding an entry."""
    return (json.dumps(each) + "\n").encode("utf-8")


def write_log(profile: Profile, *entries: dict[str, object]) -> None:
    """Write `imports.jsonl` as complete lines, one per entry."""
    profile.import_log_file.write_bytes(b"".join(map(line, entries)))


class CompleteLogTests(unittest.TestCase):
    def test_a_stored_run_is_restored_with_its_original_history(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            content = payload("01.04.2026", "30.04.2026")
            payload_id = archive(profile, "joint-current/export-20260502.csv", content)
            write_log(
                profile,
                entry("run-0001", "joint-current/export-20260502.csv", payload_id),
            )
            expected = ImportRun(
                import_run_id="run-0001",
                payload_id=payload_id,
                declared_account_id="joint-current",
                source_format="danske-csv-v1",
                original_filename="export-20260502.csv",
                exported_on=date(2026, 5, 2),
                exported_on_source="filename",
                covers_from=date(2026, 4, 1),
                covers_through=date(2026, 5, 2),
                started_at=STARTED_AT,
                outcome="stored",
                repeat_of=None,
            )

            with writer_lock(profile) as lock:
                restored = replay_import_log(lock)

            assert restored == (expected,)
            with BronzeStore(profile) as store:
                assert store.import_runs() == (expected,)
                assert store.get_payload(payload_id).content == content
                assert [
                    record.fields["Dato"]
                    for record in store.get_source_records(payload_id)
                ] == ["01.04.2026", "30.04.2026"]
                assert store.get_format_failures(payload_id) == ()

    def test_repeat_refused_and_unreadable_runs_keep_their_logged_outcomes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory))
            first = payload("01.04.2026")
            refused = payload("01.03.2026")
            unreadable = b"not an export"
            first_id = archive(profile, "joint-current/export-20260502.csv", first)
            archive(profile, "joint-current/export-20260503.csv", first)
            refused_path = f"joint-current/refused/{sha256(refused).hexdigest()[:12]}"
            refused_id = archive(profile, f"{refused_path}/old.csv", refused)
            unreadable_id = archive(profile, "joint-current/broken.csv", unreadable)
            write_log(
                profile,
                entry("run-0001", "joint-current/export-20260502.csv", first_id),
                entry(
                    "run-0002",
                    "joint-current/export-20260503.csv",
                    first_id,
                    started_at=LATER.isoformat(),
                    outcome="repeat",
                    repeat_of="run-0001",
                ),
                entry(
                    "run-0003",
                    f"{refused_path}/old.csv",
                    refused_id,
                    started_at=LATEST.isoformat(),
                    outcome="refused",
                ),
                entry(
                    "run-0004",
                    "joint-current/broken.csv",
                    unreadable_id,
                    started_at=LAST.isoformat(),
                    exported_on_source="declared",
                ),
            )

            with writer_lock(profile) as lock:
                replay_import_log(lock)

            with BronzeStore(profile) as store:
                runs = store.import_runs()
                assert [
                    (
                        run.import_run_id,
                        run.original_filename,
                        run.started_at,
                        run.outcome,
                        run.repeat_of,
                    )
                    for run in runs
                ] == [
                    ("run-0001", "export-20260502.csv", STARTED_AT, "stored", None),
                    ("run-0002", "export-20260503.csv", LATER, "repeat", "run-0001"),
                    ("run-0003", "old.csv", LATEST, "refused", None),
                    ("run-0004", "broken.csv", LAST, "stored", None),
                ]
                assert runs[3].exported_on_source == "declared"
                assert store.get_payload(refused_id).content == refused
                assert len(store.get_source_records(refused_id)) == 1
                assert store.get_source_records(unreadable_id) == ()
                assert [
                    failure.source_format
                    for failure in store.get_format_failures(unreadable_id)
                ] == ["danske-csv-v1"]


def imported_household(root: Path) -> Profile:
    """A household whose two exports were imported, archived and logged."""
    profile = household(root)
    for name, content, through in (
        ("export-20260502.csv", payload("01.04.2026"), date(2026, 5, 2)),
        ("export-20260503.csv", payload("02.05.2026"), date(2026, 5, 3)),
    ):
        source = drop(profile, "joint-current", name, content)
        with writer_lock(profile) as lock:
            import_inbox_file(lock, source, Coverage(date(2026, 4, 1), through))
    return profile


def restored_household(root: Path, original: Profile) -> Profile:
    """An empty household holding a copy of `original`'s export archive."""
    profile = household(root)
    shutil.copytree(original.exports, profile.exports)
    return profile


class PrefixTests(unittest.TestCase):
    def test_a_suffix_replays_onto_its_restored_prefix(self) -> None:
        with TemporaryDirectory() as directory:
            original = imported_household(Path(directory) / "original")
            restored = restored_household(Path(directory) / "restored", original)
            log = original.import_log_file.read_bytes()
            first_line = log[: log.index(b"\n") + 1]
            with BronzeStore(original) as store:
                first, second = store.import_runs()

            restored.import_log_file.write_bytes(first_line)
            with writer_lock(restored) as lock:
                assert replay_import_log(lock) == (first,)
            restored.import_log_file.write_bytes(log)
            with writer_lock(restored) as lock:
                assert replay_import_log(lock) == (second,)

            with BronzeStore(restored) as store:
                assert store.import_runs() == (first, second)

    def test_replaying_a_replayed_log_again_restores_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            original = imported_household(Path(directory) / "original")
            restored = restored_household(Path(directory) / "restored", original)
            shutil.copyfile(original.import_log_file, restored.import_log_file)
            with writer_lock(restored) as lock:
                replay_import_log(lock)

            with writer_lock(restored) as lock:
                assert replay_import_log(lock) == ()

            with BronzeStore(original) as before, BronzeStore(restored) as after:
                assert after.import_runs() == before.import_runs()


class ConflictTests(unittest.TestCase):
    def _two_runs(self) -> tuple[Profile, dict[str, object], dict[str, object]]:
        """A household with two archived exports and their entries, unlogged."""
        profile = household(Path(self.enterContext(TemporaryDirectory())))
        first_id = archive(profile, "joint-current/first.csv", payload("01.04.2026"))
        second_id = archive(profile, "joint-current/second.csv", payload("02.04.2026"))
        first = entry("run-0001", "joint-current/first.csv", first_id)
        second = entry(
            "run-0002",
            "joint-current/second.csv",
            second_id,
            started_at=LATER.isoformat(),
        )
        return profile, first, second

    def _replay(self, profile: Profile, *entries: dict[str, object]) -> None:
        write_log(profile, *entries)
        with writer_lock(profile) as lock:
            replay_import_log(lock)

    def _held_runs(self, profile: Profile) -> tuple[ImportRun, ...]:
        with BronzeStore(profile) as store:
            return store.import_runs()

    def test_a_run_bronze_holds_otherwise_than_logged_is_refused(self) -> None:
        other_bytes = payload("03.04.2026")
        for changes in (
            {"covers_from": "2026-03-01"},
            {"started_at": LATEST.isoformat()},
            {
                "payload_sha256": sha256(other_bytes).hexdigest(),
                "archive_path": "joint-current/other.csv",
            },
        ):
            with self.subTest(changes=sorted(changes)):
                profile, first, second = self._two_runs()
                archive(profile, "joint-current/other.csv", other_bytes)
                self._replay(profile, first | changes)
                held = self._held_runs(profile)

                with pytest.raises(RunConflictError, match="run-0001"):
                    self._replay(profile, first, second)

                assert self._held_runs(profile) == held

    def test_bronze_holding_a_later_run_but_not_the_first_is_refused(self) -> None:
        profile, first, second = self._two_runs()
        self._replay(profile, second)
        held = self._held_runs(profile)

        with pytest.raises(NotALogPrefixError):
            self._replay(profile, first, second)

        assert self._held_runs(profile) == held

    def test_bronze_holding_a_run_the_log_lacks_is_refused(self) -> None:
        profile, first, second = self._two_runs()
        self._replay(
            profile,
            first,
            entry(
                "run-0099",
                "joint-current/second.csv",
                sha256(payload("02.04.2026")).hexdigest(),
                started_at=LAST.isoformat(),
            ),
        )
        held = self._held_runs(profile)

        with pytest.raises(NotALogPrefixError):
            self._replay(profile, first, second)

        assert self._held_runs(profile) == held

    def test_a_repeat_of_a_run_not_logged_before_it_is_refused(self) -> None:
        profile, first, second = self._two_runs()

        with pytest.raises(UnknownRepeatOfError, match="run-0002"):
            self._replay(profile, first, second | {"repeat_of": "run-0009"})

        assert [run.import_run_id for run in self._held_runs(profile)] == ["run-0001"]


def _without(field: str) -> Callable[[dict[str, object]], dict[str, object]]:
    return lambda each: {key: value for key, value in each.items() if key != field}


def _with(**changes: object) -> Callable[[dict[str, object]], dict[str, object]]:
    return lambda each: each | changes


# Each one turns a valid second entry into one replay must refuse.
INVALID_ENTRIES: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {
    "a later format": _with(format=2),
    "a missing field": _without("covers_from"),
    "an extra field": _with(note="extra"),
    "a number for a string": _with(account_id=7),
    "an unknown outcome": _with(outcome="kept"),
    "an unknown export-date source": _with(exported_on_source="guessed"),
    "a repeat without its link": _with(outcome="repeat"),
    "a link on a stored run": _with(repeat_of="run-0001"),
    "an unreadable date": _with(covers_from="2026-02-30"),
    "a timestamp without an offset": _with(started_at="2026-05-03T09:00:00"),
    "a hash that is not SHA-256": _with(payload_sha256="c0ffee"),
    "another account's folder": _with(archive_path="joint-savings/second.csv"),
    "a path out of the archive": _with(archive_path="joint-current/../second.csv"),
    "a second entry for a run": _with(import_run_id="run-0001"),
}


class InvalidLogTests(unittest.TestCase):
    def _log(self) -> tuple[Profile, bytes, bytes]:
        """A household with two archived runs; return their two log lines."""
        profile = household(Path(self.enterContext(TemporaryDirectory())))
        first_id = archive(profile, "joint-current/first.csv", payload("01.04.2026"))
        second_id = archive(profile, "joint-current/second.csv", payload("02.04.2026"))
        first = entry("run-0001", "joint-current/first.csv", first_id)
        second = entry(
            "run-0002",
            "joint-current/second.csv",
            second_id,
            started_at=LATER.isoformat(),
        )
        return profile, line(first), line(second)

    def _assert_refused_at_line_2(self, profile: Profile, log: bytes) -> None:
        profile.import_log_file.write_bytes(log)
        with (
            writer_lock(profile) as lock,
            pytest.raises(ImportLogInvalidError, match="line 2") as refusal,
        ):
            replay_import_log(lock)
        assert "second.csv" not in str(refusal.value)
        with BronzeStore(profile) as store:
            assert store.import_runs() == ()

    def test_an_invalid_entry_refuses_the_log_before_anything_is_restored(
        self,
    ) -> None:
        for name, spoil in INVALID_ENTRIES.items():
            with self.subTest(name):
                profile, first, second = self._log()
                spoiled = line(spoil(json.loads(second)))

                self._assert_refused_at_line_2(profile, first + spoiled)

    def test_a_line_that_is_no_entry_refuses_the_log(self) -> None:
        for name, bad_line in (
            ("blank", b"\n"),
            ("not JSON", b"{not json\n"),
            ("not an object", b"[1, 2]\n"),
        ):
            with self.subTest(name):
                profile, first, second = self._log()

                self._assert_refused_at_line_2(profile, first + bad_line + second)

    def test_a_final_line_a_crash_cut_off_is_not_replayed(self) -> None:
        profile, first, second = self._log()
        profile.import_log_file.write_bytes(first + second[:-20])

        with writer_lock(profile) as lock:
            restored = replay_import_log(lock)

        assert [run.import_run_id for run in restored] == ["run-0001"]

    def test_no_import_log_restores_nothing(self) -> None:
        profile, _, _ = self._log()

        with writer_lock(profile) as lock:
            assert replay_import_log(lock) == ()


class ArchiveProofTests(unittest.TestCase):
    def _refused_replay(
        self, second: bytes | None, refusal: type[RuntimeError]
    ) -> tuple[Profile, str]:
        """Log two runs; archive the second's export as `second`, or not at all.

        Replay must stop with `refusal`, naming the second run but not its
        file. Returns the profile and the first run's payload hash.
        """
        directory = self.enterContext(TemporaryDirectory())
        profile = household(Path(directory))
        first_id = archive(profile, "joint-current/first.csv", payload("01.04.2026"))
        logged = payload("02.04.2026")
        if second is not None:
            archive(profile, "joint-current/second.csv", second)
        write_log(
            profile,
            entry("run-0001", "joint-current/first.csv", first_id),
            entry(
                "run-0002",
                "joint-current/second.csv",
                sha256(logged).hexdigest(),
                started_at=LATER.isoformat(),
            ),
        )
        with (
            writer_lock(profile) as lock,
            pytest.raises(refusal, match="run-0002") as raised,
        ):
            replay_import_log(lock)
        assert "second.csv" not in str(raised.value)
        return profile, first_id

    def _assert_only_the_first_run_restored(
        self, profile: Profile, first_id: str
    ) -> None:
        with BronzeStore(profile) as store:
            assert [run.import_run_id for run in store.import_runs()] == ["run-0001"]
            assert store.get_payload(first_id).payload_id == first_id
            with pytest.raises(KeyError):
                store.get_payload(sha256(payload("02.04.2026")).hexdigest())

    def test_a_missing_archived_export_stops_replay_at_its_run(self) -> None:
        profile, first_id = self._refused_replay(None, ArchivedExportMissingError)

        self._assert_only_the_first_run_restored(profile, first_id)

    def test_archived_bytes_that_do_not_match_the_entry_are_refused(self) -> None:
        profile, first_id = self._refused_replay(
            payload("03.04.2026"), ArchivedExportMismatchError
        )

        self._assert_only_the_first_run_restored(profile, first_id)
