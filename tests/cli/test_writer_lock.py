# Copyright 2026 Therkel
"""The writer lock: a second writing command refuses at once with exit 4.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test.
"""

import errno
import sqlite3
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.bronze import BronzeStore
from budget.locking import writer_lock
from tests.cli.commands import migrate
from tests.cli.processes import explicit_environment
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


class WriterLockTests(unittest.TestCase):
    def test_migrate_refuses_while_another_command_holds_the_lock(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            with writer_lock(development_profile(folder)):
                status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "another command is running" in stderr
            assert not development_profile(folder).bronze_store.exists()

            assert migrate(profile_file)[0] == EXIT_OK
            with BronzeStore(development_profile(folder)):
                pass


def _patched_platform_lock(error: OSError) -> AbstractContextManager[object]:
    """Make the operating system's lock call fail with `error`."""
    target = "msvcrt.locking" if sys.platform == "win32" else "fcntl.flock"
    return mock.patch(target, side_effect=error)


class UnusableStoresFolderTests(unittest.TestCase):
    def test_a_stores_folder_that_cannot_be_created_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            not_a_folder = folder / "not-a-folder"
            not_a_folder.write_text("", encoding="utf-8")
            profile_file = write_profile(folder, stores=not_a_folder / "stores")

            status, stderr = migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "cannot be used" in stderr

    def test_a_lock_failure_that_is_not_contention_is_not_reported_as_one(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            no_locks = OSError(errno.ENOLCK, "No locks available")

            with _patched_platform_lock(no_locks):
                status, stderr = migrate(write_profile(folder))

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "cannot be used" in stderr
            assert "another command" not in stderr
            assert not development_profile(folder).bronze_store.exists()


# Guards rather than red tests: the operating system and the `with` block
# release the lock, so these passed as soon as the lock existed.
_HOLD_THE_LOCK = """
import sys, time
from pathlib import Path
from budget.locking import writer_lock
from budget.profiles import Profile
stores = Path(sys.argv[1])
profile = Profile(name="development", stores=stores, inputs=stores.parent / "inputs")
with writer_lock(profile):
    print("held", flush=True)
    time.sleep(60)
"""


def _first_line(holder: subprocess.Popen[str], *, timeout: float) -> str:
    """Read the child's first line, failing rather than hanging past `timeout`.

    The caller kills the child on failure, which ends the pending read.
    """
    assert holder.stdout is not None
    reader = ThreadPoolExecutor(max_workers=1)
    try:
        return reader.submit(holder.stdout.readline).result(timeout=timeout)
    finally:
        reader.shutdown(wait=False)


def _migrate_once_released(profile_file: Path, *, within: float) -> int:
    """Run `migrate`, retrying only while the lock is still reported held.

    Windows releases a dead process's locks asynchronously: `wait()` can
    return before the lock is free, so one immediate retry is a race.
    """
    deadline = time.monotonic() + within
    while True:
        status, stderr = migrate(profile_file)
        if "another command is running" not in stderr or time.monotonic() > deadline:
            return status
        time.sleep(0.05)


class WriterLockReleaseTests(unittest.TestCase):
    def test_a_refused_command_releases_the_lock(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            store = development_profile(folder).bronze_store
            with closing(sqlite3.connect(store)) as connection:
                connection.execute("PRAGMA user_version = 99")

            assert migrate(profile_file)[0] == EXIT_REFUSED_ENVIRONMENT

            with writer_lock(development_profile(folder)):
                pass

    def test_a_killed_command_releases_the_lock(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            # Leaving the `with` block closes the pipe and waits for the child.
            with subprocess.Popen(
                [sys.executable, "-c", _HOLD_THE_LOCK, str(folder / "stores")],
                stdout=subprocess.PIPE,
                env=explicit_environment(),
                text=True,
            ) as holder:
                try:
                    assert _first_line(holder, timeout=30).strip() == "held"
                    assert migrate(profile_file)[0] == EXIT_REFUSED_ENVIRONMENT

                    holder.kill()
                    holder.wait(timeout=30)

                    assert _migrate_once_released(profile_file, within=10) == EXIT_OK
                finally:
                    holder.kill()


if __name__ == "__main__":
    unittest.main()
