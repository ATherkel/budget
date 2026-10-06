# Copyright 2026 Therkel
"""Safety pins around `budget rebuild`: what must not change.

Unchanged Bronze rebuilds to the same result; a competing writer refuses and
keeps the stored result; a replacement SQLite refuses leaves the previous
result and no success log; a quarantined run keeps its real reason codes through
a repeat; an unbuilt stage and a missing store refuse. Every case here already
holds, so these are pins, not claimed reds. Each test is synthetic, passes
`main` an explicit environment, and names independent expected values.
"""

import json
import sqlite3
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.silver import SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import ACCOUNTS, drop, payload

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
FIRST_EXPORT = "danske-20260305.csv"
LATER_EXPORT = "danske-20260403.csv"
START = date(2026, 3, 1)
# A payload whose header is not a `danske-csv-v1` header: a format failure.
GARBAGE = b'"Nope","Nope"\r\n1,2\r\n'


def _profile(profile_file: Path, folder: Path) -> Profile:
    """Migrate both stores and write the synthetic `accounts.toml`."""
    assert migrate(profile_file)[0] == EXIT_OK
    profile = development_profile(folder)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


def _import_one(profile: Profile, name: str, content: bytes, through: date) -> None:
    """Import one synthetic export, as `budget import` will."""
    source = drop(profile, "joint-current", name, content)
    with writer_lock(profile) as lock:
        import_inbox_file(
            lock, source, Coverage(covers_from=START, covers_through=through)
        )


def _records(profile: Profile) -> list[dict[str, object]]:
    """Every routine log record the profile holds, parsed."""
    folder = profile.stores / "logs"
    paths = sorted(folder.rglob("*.jsonl")) if folder.is_dir() else []
    return [
        json.loads(line)
        for path in paths
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _block_transaction_inserts(profile: Profile) -> None:
    """Make the Silver store refuse every new transaction row, at SQLite."""
    with closing(sqlite3.connect(profile.silver_store)) as connection:
        connection.execute(
            "CREATE TRIGGER refuse_transactions BEFORE INSERT ON transactions "
            "BEGIN SELECT RAISE(ABORT, 'blocked'); END;"
        )
        connection.commit()


class RebuildSafetyTests(unittest.TestCase):
    def test_unchanged_bronze_stores_the_same_nonempty_result(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _profile(profile_file, folder)
            _import_one(profile, FIRST_EXPORT, payload("01.03.2026"), date(2026, 3, 4))

            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
            with SilverStore(profile) as store:
                first = store.read()
            assert [t.description for t in first.transactions] == ["Café"]

            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
            with SilverStore(profile) as store:
                assert store.read() == first

    def test_a_competing_writer_refuses_and_keeps_the_previous_result(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _profile(profile_file, folder)
            _import_one(profile, FIRST_EXPORT, payload("01.03.2026"), date(2026, 3, 4))
            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
            with SilverStore(profile) as store:
                before = store.read()

            with writer_lock(profile):
                status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "another command is running" in stderr
            with SilverStore(profile) as store:
                assert store.read() == before

    def test_a_failed_replacement_keeps_the_result_and_logs_no_success(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _profile(profile_file, folder)
            _import_one(profile, FIRST_EXPORT, payload("01.03.2026"), date(2026, 3, 4))
            assert rebuild(profile_file, "--from", "silver")[0] == EXIT_OK
            with SilverStore(profile) as store:
                before = store.read()
            logged = len(_records(profile))
            _import_one(profile, LATER_EXPORT, payload("02.04.2026"), date(2026, 4, 2))
            _block_transaction_inserts(profile)

            with pytest.raises(sqlite3.IntegrityError):
                rebuild(profile_file, "--from", "silver")

            with SilverStore(profile) as store:
                assert store.read() == before
            assert len(_records(profile)) == logged

    def test_a_format_failure_keeps_its_codes_through_a_repeat(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = _profile(profile_file, folder)
            _import_one(profile, FIRST_EXPORT, GARBAGE, date(2026, 3, 4))
            _import_one(profile, "danske-20260312.csv", GARBAGE, date(2026, 3, 11))

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            with SilverStore(profile) as store:
                result = store.read()
            assert [error.code for error in result.import_run_results[0].errors] == [
                "format-failure"
            ]
            assert "quarantined  format-failure" in stdout
            assert "repeat quarantined  format-failure" in stdout

    def test_a_missing_store_refuses(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            profile.inputs.mkdir(parents=True, exist_ok=True)
            profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")

            status, _, stderr = rebuild(profile_file, "--from", "silver")
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "no Bronze store" in stderr

            assert migrate(profile_file, "--stage", "bronze")[0] == EXIT_OK
            status, _, stderr = rebuild(profile_file, "--from", "silver")
            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "no Silver store" in stderr

    def test_an_unbuilt_stage_refuses(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            for stage in ("gold", "bronze"):
                with self.subTest(stage=stage):
                    status, _, stderr = rebuild(profile_file, "--from", stage)

                    assert status == EXIT_REFUSED_ENVIRONMENT
                    assert "not built yet" in stderr


if __name__ == "__main__":
    unittest.main()
