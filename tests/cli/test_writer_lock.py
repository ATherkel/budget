# Copyright 2026 Therkel
"""The writer lock: a second writing command refuses at once with exit 4.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test.
"""

import io
import sqlite3
import subprocess
import sys
import unittest
from contextlib import closing, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.bronze import BronzeStore
from budget.cli import main
from budget.locking import writer_lock
from budget.profiles import Profile
from tests.cli.processes import explicit_environment
from tests.cli.profile_files import write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


def _development(folder: Path) -> Profile:
    """The development profile `write_profile` describes inside `folder`."""
    return Profile(name="development", stores=folder / "stores")


def _migrate(profile_file: Path) -> tuple[int, str]:
    """Run `budget migrate` with one profile file; return status and stderr."""
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        status = main(["--profile", str(profile_file), "migrate"], environ={})
    return status, stderr.getvalue()


class WriterLockTests(unittest.TestCase):
    def test_migrate_refuses_while_another_command_holds_the_lock(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)

            with writer_lock(_development(folder)):
                status, stderr = _migrate(profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert "another command is running" in stderr
            assert not _development(folder).bronze_store.exists()

            assert _migrate(profile_file)[0] == EXIT_OK
            with BronzeStore(_development(folder)):
                pass


# Guards rather than red tests: the operating system and the `with` block
# release the lock, so these passed as soon as the lock existed.
_HOLD_THE_LOCK = """
import sys, time
from pathlib import Path
from budget.locking import writer_lock
from budget.profiles import Profile
with writer_lock(Profile(name="development", stores=Path(sys.argv[1]))):
    print("held", flush=True)
    time.sleep(60)
"""


class WriterLockReleaseTests(unittest.TestCase):
    def test_a_refused_command_releases_the_lock(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert _migrate(profile_file)[0] == EXIT_OK
            store = _development(folder).bronze_store
            with closing(sqlite3.connect(store)) as connection:
                connection.execute("PRAGMA user_version = 99")

            assert _migrate(profile_file)[0] == EXIT_REFUSED_ENVIRONMENT

            with writer_lock(_development(folder)):
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
                    assert holder.stdout is not None
                    assert holder.stdout.readline().strip() == "held"
                    assert _migrate(profile_file)[0] == EXIT_REFUSED_ENVIRONMENT

                    holder.kill()
                    holder.wait(timeout=30)

                    assert _migrate(profile_file)[0] == EXIT_OK
                finally:
                    holder.kill()


if __name__ == "__main__":
    unittest.main()
