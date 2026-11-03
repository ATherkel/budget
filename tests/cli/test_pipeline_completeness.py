# Copyright 2026 Therkel
"""`import` and `rebuild` end with the completeness output `status` prints.

Every profile is synthetic. The seam is the CLI itself: a test reads what an
operator reads at the end of a pipeline command and compares it with what
`status` prints for the same profile afterwards.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.cli.commands import import_, migrate, rebuild, status
from tests.cli.imports import write_ranges
from tests.cli.pipelines import household, write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import chained_payload, drop, payload

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

    def test_a_rebuild_that_publishes_nothing_still_ends_with_it(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK

            code, stdout, stderr = rebuild(built.profile_file)
            _, shown_by_status, _ = status(built.profile_file)

            assert (code, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            assert stdout.endswith(shown_by_status)


class ImportCompletenessTests(unittest.TestCase):
    def test_import_ends_with_the_completeness_status_prints(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            write_inputs(profile)
            ranges = write_ranges(folder, default=("2026-03-01", "2026-03-09"))
            drop(profile, "joint-current", "danske-20260310.csv", payload("01.03.2026"))

            code, stdout, stderr = import_(profile_file, "--ranges", str(ranges))
            _, shown_by_status, _ = status(profile_file)

            assert (code, stderr) == (EXIT_OK, "")
            assert PUBLISHED_HEADING in shown_by_status
            assert stdout.endswith(shown_by_status)

    def test_the_unclassified_money_it_prints_never_reaches_the_routine_log(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            write_inputs(profile)
            ranges = write_ranges(folder, default=("2026-03-01", "2026-03-09"))
            drop(profile, "joint-current", "danske-20260310.csv", payload("01.03.2026"))
            assert import_(profile_file, "--ranges", str(ranges))[0] == EXIT_OK
            drop(
                profile,
                "joint-current",
                "danske-20260311.csv",
                chained_payload("01.03.2026", "02.03.2026"),
            )

            code, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (code, stderr) == (EXIT_OK, "")
            assert "out -90.00 DKK, 2 transactions" in stdout
            log = profile.log_file("commands.jsonl").read_text(encoding="utf-8")
            assert "90.00" not in log
