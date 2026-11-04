# Copyright 2026 Therkel
"""`budget check`: validate every input and the decision-log prefix, read-only.

Every profile, input and decision is synthetic. The seam is the CLI itself,
so these tests observe what an operator reads and the exit status.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.cli.commands import check
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0


def _everything_under(folder: Path) -> list[str]:
    """Every path under `folder`, relative to it, in order."""
    return sorted(str(path.relative_to(folder)) for path in folder.rglob("*"))


class CheckCommandTests(unittest.TestCase):
    def test_valid_inputs_without_a_gold_store_pass_and_create_nothing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            write_inputs(development_profile(folder))
            before = _everything_under(folder)

            code, stdout, stderr = check(profile_file)

            assert (code, stdout, stderr) == (EXIT_OK, "No problems found.\n", "")
            assert _everything_under(folder) == before
