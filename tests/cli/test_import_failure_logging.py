# Copyright 2026 Therkel
"""`budget import` stopped by an operating-system error logs no path.

An inbox file can vanish or be locked by another program after the preview has
read it and before the import reads it again, first to check for an
interrupted run of the same file. The OS error then propagates as an
unexpected error, and its text names the file's full path: the account folder
and a filename that carries the bank account number. The routine log may never
hold any of them, whatever event a later change adds for such a failure. Every
account, date, text and amount is synthetic.
"""

import errno
import json
import unittest
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

from budget.profiles import Profile
from budget.routine_logging import LOG_FILE, LOG_FOLDER, ROTATED_LOG_FILE
from tests.cli.commands import import_, migrate
from tests.cli.imports import write_ranges
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import drop, payload

EXIT_OK = 0
ACCOUNT_ID = "joint-current"
# The synthetic household's bank account number for `joint-current`.
ACCOUNT_NUMBER = "0012345678"
FAILING_NAME = f"Konto-{ACCOUNT_NUMBER}-20260306.csv"
# The preview reads an inbox file once; every later read is the import's.
PREVIEW_READS = 1


def _gone(path: Path) -> OSError:
    """The error a read raises for a file removed from the inbox."""
    return FileNotFoundError(errno.ENOENT, "No such file or directory", str(path))


def _locked(path: Path) -> OSError:
    """The error Windows raises for a file another program holds."""
    return PermissionError(
        errno.EACCES,
        "The process cannot access the file because it is being used by "
        "another process",
        str(path),
    )


def _routine_log_text(profile: Profile) -> str:
    """Every routine-log record, current and rotated, as one text."""
    logs = profile.stores / LOG_FOLDER
    return "".join(
        (logs / name).read_text(encoding="utf-8")
        for name in (ROTATED_LOG_FILE, LOG_FILE)
        if (logs / name).exists()
    )


class ImportFailureLoggingTests(unittest.TestCase):
    def _import_fails_with(self, fault: Callable[[Path], OSError]) -> None:
        """Import once, then fail the import's reads of a second file."""
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            write_inputs(profile)
            ranges = write_ranges(folder, default=("2026-03-01", "2026-03-04"))
            drop(profile, ACCOUNT_ID, "danske-20260305.csv", payload("01.03.2026"))
            assert import_(profile_file, "--ranges", str(ranges))[0] == EXIT_OK
            logged_before = _routine_log_text(profile)
            assert logged_before

            failing = drop(profile, ACCOUNT_ID, FAILING_NAME, payload("02.03.2026"))
            read_bytes = Path.read_bytes
            reads: list[Path] = []

            def faulty_later_read(path: Path) -> bytes:
                reads.append(path)
                if path == failing and reads.count(path) > PREVIEW_READS:
                    raise fault(path)
                return read_bytes(path)

            raised = fault(failing)
            with (
                mock.patch.object(
                    Path, "read_bytes", autospec=True, side_effect=faulty_later_read
                ),
                pytest.raises(type(raised)) as caught,
            ):
                import_(profile_file, "--ranges", str(ranges))

            # The error propagates as before, still naming the file.
            assert str(caught.value) == str(raised)
            logged = _routine_log_text(profile)
            assert logged.startswith(logged_before)
            assert all(json.loads(line) for line in logged.splitlines())
            for leaked in (
                str(failing),
                str(failing.parent),
                FAILING_NAME,
                ACCOUNT_NUMBER,
                ACCOUNT_ID,
            ):
                # As a log line writes it: a Windows path's backslashes doubled.
                encoded = json.dumps(leaked, ensure_ascii=False)[1:-1]
                assert encoded not in logged, leaked

    def test_a_file_that_vanishes_mid_import_leaves_no_path_in_the_log(
        self,
    ) -> None:
        self._import_fails_with(_gone)

    def test_a_file_locked_mid_import_leaves_no_path_in_the_log(self) -> None:
        self._import_fails_with(_locked)


if __name__ == "__main__":
    unittest.main()
