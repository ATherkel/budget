# Copyright 2026 Therkel
"""`import` and `rebuild` end with the completeness output `status` prints.

Every profile is synthetic. The seam is the CLI itself: a test reads what an
operator reads at the end of a pipeline command and compares it with what
`status` prints for the same profile afterwards.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.cli.commands import rebuild, status
from tests.cli.pipelines import household

EXIT_OK = 0
PUBLISHED_HEADING = "Published figures: publication 1 (current)"


class RebuildCompletenessTests(unittest.TestCase):
    def test_rebuild_ends_with_the_completeness_status_prints(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))

            code, stdout, stderr = rebuild(built.profile_file)
            _, shown_by_status, _ = status(built.profile_file)

            assert (code, stderr) == (EXIT_OK, "")
            assert PUBLISHED_HEADING in shown_by_status
            assert stdout.endswith(shown_by_status)
