# Copyright 2026 Therkel
"""Usage errors: `main` returns argparse's own exit status, 2.

Commands this code does not have yet are usage errors, not silent
simulations of a pipeline that does not exist.
"""

import io
import unittest
from contextlib import redirect_stderr

from budget.cli import main

EXIT_USAGE = 2


class UsageTests(unittest.TestCase):
    def test_a_usage_error_returns_exit_2(self) -> None:
        cases = {
            "no command": [],
            "a command not built yet": ["import"],
            "another command not built yet": ["rebuild", "--from", "silver"],
            "an unknown stage": ["migrate", "--stage", "platinum"],
            "an unknown option": ["migrate", "--force"],
        }
        for case, argv in cases.items():
            with self.subTest(case):
                stderr = io.StringIO()

                with redirect_stderr(stderr):
                    status = main(argv, environ={})

                assert status == EXIT_USAGE
                assert "usage: budget" in stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
