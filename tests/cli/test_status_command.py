# Copyright 2026 Therkel
"""`budget status`: balance and classification completeness, read-only.

Every profile and result is synthetic. The seam is the CLI itself, so these
tests observe what an operator reads, not the report objects behind it.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.cli.commands import status
from tests.cli.profile_files import write_profile

EXIT_OK = 0
NOTHING_PUBLISHED = "Published figures: unavailable, nothing is published"


def _everything_under(folder: Path) -> list[str]:
    """Every path under `folder`, relative to it, in a fixed order."""
    return sorted(str(path.relative_to(folder)) for path in folder.rglob("*"))


class StatusCommandTests(unittest.TestCase):
    def test_status_marks_published_figures_unavailable_and_creates_nothing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            before = _everything_under(folder)

            code, stdout, stderr = status(profile_file)

            assert (code, stderr) == (EXIT_OK, "")
            assert NOTHING_PUBLISHED in stdout.splitlines()
            assert _everything_under(folder) == before


if __name__ == "__main__":
    unittest.main()
