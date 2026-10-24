# Copyright 2026 Therkel
"""A production `budget rebuild` of Gold runs only from committed code.

The Git check is the system boundary, so these tests replace `subprocess.run`.
No test opens a real profile or store.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from budget.gold.store import GoldStore
from tests.cli.commands import rebuild
from tests.cli.pipelines import household

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
DIRTY_STATUS = " M src/budget/cli.py\n"


def _git(stdout: str) -> mock.Mock:
    """A finished Git process that succeeded and printed `stdout`."""
    completed = mock.Mock()
    completed.returncode = 0
    completed.stdout = stdout
    completed.stderr = ""
    return completed


class ProductionGoldCodeTests(unittest.TestCase):
    def test_a_production_gold_rebuild_refuses_uncommitted_code(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")

            with mock.patch("subprocess.run", return_value=_git(DIRTY_STATUS)):
                status, stdout, stderr = rebuild(built.profile_file)

            assert status == EXIT_REFUSED_ENVIRONMENT
            assert stdout == ""
            assert "uncommitted" in stderr
            assert "nothing was written" in stderr
            with GoldStore(built.profile) as gold:
                assert gold.current() is None
                assert gold.pointer_history() == ()


COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _clean_checkout(arguments: list[str], **_: object) -> mock.Mock:
    """Answer the fixed Git commands of a clean checkout at `COMMIT`."""
    return _git(COMMIT + "\n" if "rev-parse" in arguments else "")


class ProductionRecipeTests(unittest.TestCase):
    def test_a_production_recipe_names_the_commit_it_was_built_from(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory), name="production")

            with mock.patch("subprocess.run", side_effect=_clean_checkout):
                status, _, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            with GoldStore(built.profile) as gold:
                assert gold.recipe(1).code_version == COMMIT


if __name__ == "__main__":
    unittest.main()
