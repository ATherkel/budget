# Copyright 2026 Therkel
"""`budget import` stores, then builds and publishes what it stored.

Every test passes `main` an explicit environment. The publications are read
back through `GoldStore`, so a test sees what a dashboard would.
"""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from tests.cli.commands import import_, migrate
from tests.cli.imports import write_ranges
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import drop, payload

EXIT_OK = 0


class ImportPublishesTests(unittest.TestCase):
    def test_each_import_that_stores_something_publishes_a_publication(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            write_inputs(profile)
            ranges = write_ranges(folder, default=("2026-03-01", "2026-03-09"))
            drop(profile, "joint-current", "danske-20260310.csv", payload("01.03.2026"))

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 1" in stdout
            with GoldStore(profile) as gold:
                transactions = gold.open(1).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
            assert [t.description for t in transactions] == ["Café"]
            drop(profile, "joint-current", "danske-20260311.csv", payload("02.03.2026"))

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with GoldStore(profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1, 2]


if __name__ == "__main__":
    unittest.main()
