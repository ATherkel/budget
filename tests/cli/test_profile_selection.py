# Copyright 2026 Therkel
"""Selecting a profile: `--profile`, `BUDGET_PROFILE`, and no default.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test.
"""

import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.bronze import BronzeStore
from budget.bronze.storage import StoreNotFoundError
from budget.cli import main
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4


class ProfileSelectionTests(unittest.TestCase):
    def test_a_command_without_a_profile_refuses(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            status = main(["migrate"], environ={})

        assert status == EXIT_REFUSED_ENVIRONMENT
        assert "--profile" in stderr.getvalue()
        assert "BUDGET_PROFILE" in stderr.getvalue()

    def test_budget_profile_selects_and_the_argument_takes_precedence(self) -> None:
        with TemporaryDirectory() as directory:
            from_argument = Path(directory) / "argument"
            from_variable = Path(directory) / "variable"
            from_argument.mkdir()
            from_variable.mkdir()
            argument_file = write_profile(from_argument)
            variable_file = write_profile(from_variable)
            environ = {"BUDGET_PROFILE": str(variable_file)}
            argv = ["--profile", str(argument_file), "migrate"]

            assert main(argv, environ=environ) == EXIT_OK

            with BronzeStore(development_profile(from_argument)):
                pass
            with pytest.raises(StoreNotFoundError):
                BronzeStore(development_profile(from_variable))

            assert main(["migrate"], environ=environ) == EXIT_OK

            with BronzeStore(development_profile(from_variable)):
                pass


if __name__ == "__main__":
    unittest.main()
