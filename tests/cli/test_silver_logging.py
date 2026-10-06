# Copyright 2026 Therkel
"""Routine JSON Lines logs for `rebuild` and `review`.

Both commands record a finished event under the profile's `logs` folder, and
those records carry only what `operations.md` (*Logging*) allows: the command,
profile, event, counts, durations, versions, error codes and the identifiers.
No amount, balance, description, bank category, filename, bank account number,
account id, payload id, review id or transaction id may reach a routine log.
Every test passes `main` an explicit environment.
"""

import json
import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.routine_logging import (
    LOG_FILE,
    LOG_FOLDER,
    LOG_MAX_BYTES,
    ROTATED_LOG_FILE,
)
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild, review
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload
from tests.silver.exports import identity

EXIT_OK = 0
EXPORT_FILE = "danske-20260305.csv"
BANK_NUMBER = "0012345678"
# The keys `operations.md` allows in a routine log record.
ALLOWED_KEYS = frozenset(
    {
        "command",
        "profile",
        "event",
        "counts",
        "duration_ms",
        "code_version",
        "schema_version",
        "error_codes",
        "import_run_id",
        "publication_id",
        "decision_id",
        "review_item_kinds",
    }
)


def _log_files(profile: Profile) -> list[Path]:
    """Every routine log file under the profile's `logs` folder."""
    folder = profile.stores / LOG_FOLDER
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.rglob("*") if path.is_file())


def _log_records(profile: Profile) -> list[dict[str, object]]:
    """Every parseable JSON Lines record the routine logs hold."""
    files = _log_files(profile)
    assert files, "no routine log files under the profile's logs folder"
    records: list[dict[str, object]] = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            assert line.strip(), f"a blank line in {path.name}"
            records.append(json.loads(line))
    return records


class SilverLoggingTests(unittest.TestCase):
    def test_import_rebuild_and_review_write_safe_routine_logs(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
            content = payload("01.03.2026")
            source = drop(profile, "joint-current", EXPORT_FILE, content)
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock,
                    source,
                    Coverage(
                        covers_from=date(2026, 3, 1),
                        covers_through=date(2026, 3, 4),
                    ),
                )

            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
            assert review(profile_file)[0] == EXIT_OK

            records = _log_records(profile)
            finished = {
                str(record["command"])
                for record in records
                if record.get("event") == "finished"
            }
            assert finished >= {"rebuild", "review"}
            for record in records:
                assert {"command", "profile", "event"} <= set(record)
                assert set(record) <= ALLOWED_KEYS
                assert record["profile"] == "development"

            # Nothing a bank said, and no identifier kept for a different
            # purpose, reaches a routine log: neither in the raw bytes nor in
            # the decoded records, so a `\u00e9` escape cannot hide a
            # description, and both written forms of an amount count.
            text = "\n".join(
                path.read_text(encoding="utf-8") for path in _log_files(profile)
            )
            decoded = json.dumps(records, ensure_ascii=False, sort_keys=True)
            for leaked in (
                "-45,00",
                "955,00",
                "-45.00",
                "955.00",
                "Café",
                "Mad",
                "Dagligvarer",
                EXPORT_FILE,
                BANK_NUMBER,
                "joint-current",
                sha256(content).hexdigest(),
                identity(date(2026, 3, 1), "-45.00", "Café", 1),
            ):
                assert leaked not in text
                assert leaked not in decoded

    def test_a_full_log_rotates_before_the_next_record(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            logs = profile.stores / LOG_FOLDER
            logs.mkdir(parents=True, exist_ok=True)
            (logs / LOG_FILE).write_text(
                '{"filler": "' + "x" * LOG_MAX_BYTES + '"}\n', encoding="utf-8"
            )

            assert review(profile_file)[0] == EXIT_OK

            assert (logs / ROTATED_LOG_FILE).is_file()
            assert (logs / LOG_FILE).stat().st_size < LOG_MAX_BYTES

    def test_a_log_that_cannot_be_written_only_warns(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
            source = drop(profile, "joint-current", EXPORT_FILE, payload("01.03.2026"))
            with writer_lock(profile) as lock:
                import_inbox_file(
                    lock, source, Coverage(date(2026, 3, 1), date(2026, 3, 4))
                )
            # A file where the logs folder must go: every log write fails.
            (profile.stores / LOG_FOLDER).write_text("not a folder", encoding="utf-8")

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_OK
            assert "joint-current  accepted" in stdout
            assert "the routine log could not be written" in stderr
            with SilverStore(profile) as store:
                stored = store.read()
            assert [t.description for t in stored.transactions] == ["Café"]


if __name__ == "__main__":
    unittest.main()
