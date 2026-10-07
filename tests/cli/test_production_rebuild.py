# Copyright 2026 Therkel
"""`budget rebuild` refuses a production build from uncommitted code.

Production runs the code its own clean checkout holds, so a rebuild in a dirty
one refuses before it reads or replaces anything (operations.md, *Development
diverges from a stage*). The Git check is the system boundary, so these tests
replace `subprocess.run`; no test opens a real profile or store.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import budget
from budget.profiles import Profile, load_profile_file
from budget.silver import SilverResult, SilverStore
from tests.cli.commands import migrate, rebuild
from tests.cli.profile_files import write_profile
from tests.importing.households import ACCOUNTS

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
DIRTY_STATUS = " M src/budget/cli.py\n"
EMPTY_RESULT = SilverResult((), (), (), (), (), (), ())


def _git(returncode: int, stdout: str) -> mock.Mock:
    """A finished `git status` process, as `subprocess.run` returns one."""
    completed = mock.Mock()
    completed.returncode = returncode
    completed.stdout = stdout
    completed.stderr = ""
    return completed


def _profile_file(root: Path, name: str) -> Path:
    """Write a synthetic profile file in its own folder under `root`."""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    return write_profile(folder, name=name)


def _write_accounts(profile_file: Path) -> Profile:
    """Write the synthetic `accounts.toml` the profile's rebuild reads."""
    profile = load_profile_file(profile_file)
    profile.inputs.mkdir(parents=True, exist_ok=True)
    profile.accounts_file.write_text(ACCOUNTS, encoding="utf-8")
    return profile


class ProductionRebuildCodeTests(unittest.TestCase):
    def test_a_production_rebuild_refuses_uncommitted_code(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            production_file = _profile_file(root, "production")
            development_file = _profile_file(root, "development")
            assert migrate(production_file, "--new-store") == (EXIT_OK, "")
            production = _write_accounts(production_file)
            assert migrate(development_file)[0] == EXIT_OK
            development = _write_accounts(development_file)

            # Dirty code: refuse before anything is read or replaced.
            with mock.patch("subprocess.run", return_value=_git(0, DIRTY_STATUS)):
                status, stdout, stderr = rebuild(production_file, "--from", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "uncommitted" in stderr
            assert "nothing was written" in stderr
            # Git's own output never reaches the operator.
            assert DIRTY_STATUS.strip() not in stderr
            with SilverStore(production) as store:
                assert store.read() == EMPTY_RESULT

            # Clean code: the same command runs, like it does in development.
            run = mock.Mock(return_value=_git(0, ""))
            with mock.patch("subprocess.run", run):
                status, produced, stderr = rebuild(production_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            called = run.call_args
            assert called is not None
            arguments, kwargs = called
            # A PATH-resolved absolute executable, `git` or `git.exe`, running
            # the fixed `git status` command.
            assert Path(arguments[0][0]).name.startswith("git")
            assert arguments[0][1:] == [
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ]
            # The check reads the package's own checkout, not this profile.
            assert (
                Path(budget.__file__)
                .resolve()
                .parent.is_relative_to(Path(kwargs["cwd"]).resolve())
            )
            development_status, developed, development_stderr = rebuild(
                development_file, "--from", "silver"
            )
            assert (development_status, development_stderr) == (EXIT_OK, "")
            assert produced == developed
            with SilverStore(production) as store:
                production_result = store.read()
            with SilverStore(development) as store:
                assert production_result == store.read()

            # Code whose state cannot be checked refuses the same way.
            with mock.patch("subprocess.run", side_effect=FileNotFoundError("git")):
                status, stdout, stderr = rebuild(production_file, "--from", "silver")

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "cannot be checked" in stderr
            assert "nothing was written" in stderr
            with SilverStore(production) as store:
                assert store.read() == production_result


if __name__ == "__main__":
    unittest.main()
