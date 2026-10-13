# Copyright 2026 Therkel
"""Replaying `imports.jsonl` into Bronze from the export archive.

Every test writes a synthetic archive and import log by hand into a migrated,
empty test profile, replays them under the writer lock, and reads the restored
history back through the reopened Bronze store. The expected runs are written
out independently of the code that writes the log.
"""

import json
import unittest
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import BronzeStore, ImportRun
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.replaying import replay_import_log
from tests.importing.households import household, payload

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


def write_log(profile: Profile, *entries: dict[str, object]) -> None:
    """Write `imports.jsonl` as complete lines, one per entry."""
    profile.import_log_file.write_text(
        "".join(json.dumps(each) + "\n" for each in entries), encoding="utf-8"
    )


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
