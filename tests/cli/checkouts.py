# Copyright 2026 Therkel
"""Run production commands as from a clean checkout at a fixed commit.

A production build runs only from committed code, which it proves by asking
Git. Git is the system boundary, so tests answer for it: every test in a
`CleanCheckoutTestCase` sees a clean checkout at `COMMIT`.
"""

import unittest
from typing import override
from unittest import mock

from tests.cli.test_production_rebuild_gold import COMMIT, _clean_checkout

__all__ = ["COMMIT", "CleanCheckoutTestCase"]


class CleanCheckoutTestCase(unittest.TestCase):
    """A test case whose production builds see a clean checkout at `COMMIT`."""

    @override
    def setUp(self) -> None:
        """Answer every Git command as a clean checkout would."""
        super().setUp()
        self.enterContext(mock.patch("subprocess.run", side_effect=_clean_checkout))
