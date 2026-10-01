# Copyright 2026 Therkel
"""The `budget` command line: profile selection, migration and exit statuses.

Every test passes `main` an explicit environment, so a `BUDGET_PROFILE` set in
the operator's shell never reaches a test. Profile files are synthetic TOML
written into the test's own temporary folder.
"""

import io
import unittest
from contextlib import redirect_stderr

from budget.cli import main

EXIT_REFUSED_ENVIRONMENT = 4


class ProfileSelectionTests(unittest.TestCase):
    def test_a_command_without_a_profile_refuses(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            status = main(["migrate"], environ={})

        assert status == EXIT_REFUSED_ENVIRONMENT
        assert "--profile" in stderr.getvalue()
        assert "BUDGET_PROFILE" in stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
