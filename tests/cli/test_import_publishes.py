# Copyright 2026 Therkel
"""`budget import` stores, then builds and publishes what it stored.

Every test passes `main` an explicit environment. The publications are read
back through `GoldStore`, so a test sees what a dashboard would.
"""

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from budget.silver.store import SilverStore
from tests.cli.commands import import_, migrate, rebuild
from tests.cli.imports import write_ranges
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile
from tests.importing.households import chained_payload, drop, payload

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
            assert (
                "Changes  no previous publication to compare; publication 1 is current."
            ) in stdout
            with GoldStore(profile) as gold:
                transactions = gold.open(1).transactions(
                    start_date=date(2026, 3, 1), end_date=date(2026, 3, 31)
                )
            assert [t.description for t in transactions] == ["Café"]
            drop(
                profile,
                "joint-current",
                "danske-20260311.csv",
                chained_payload("01.03.2026", "02.03.2026"),
            )

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            assert (
                "Changes  2026-03 joint-current: "
                "unclassified out -45.00 DKK; unclassified count +1"
            ) in stdout
            assert "Review  1 unclassified opened" in stdout
            with GoldStore(profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1, 2]
            log = profile.log_file("commands.jsonl").read_text(encoding="utf-8")
            assert "-45.00" not in log

    def test_a_silver_review_item_opens_and_closes_in_the_printed_diff(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            assert migrate(profile_file)[0] == EXIT_OK
            profile = development_profile(folder)
            write_inputs(profile)
            ranges = write_ranges(folder, default=("2026-03-01", "2026-03-09"))
            drop(profile, "joint-current", "danske-20260310.csv", payload("01.03.2026"))
            assert import_(profile_file, "--ranges", str(ranges))[0] == EXIT_OK
            # Two rows that state the same balance after spending: the chain
            # breaks, so Silver quarantines the run and raises a review item.
            drop(
                profile,
                "joint-current",
                "danske-20260311.csv",
                payload("04.03.2026", "05.03.2026"),
            )

            status, stdout, stderr = import_(profile_file, "--ranges", str(ranges))

            assert (status, stderr) == (EXIT_OK, "")
            assert "Review  1 balance-break opened" in stdout
            assert "no measure or review item changed" not in stdout
            with SilverStore(profile) as silver:
                quarantined = next(
                    run.import_run_id
                    for run in silver.read().import_run_results
                    if run.status == "quarantined"
                )
            profile.input_file("decisions.jsonl").write_text(
                json.dumps(
                    {
                        "format": 1,
                        "entry": 1,
                        "decision_id": "d-0001",
                        "recorded_at": "2026-03-12T09:00:00Z",
                        "kind": "accept-discrepancy",
                        "targets": [quarantined],
                        "reason": "The bank repeated a balance",
                        "supersedes": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            status, stdout, stderr = rebuild(profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            # Accepting the run admits it, so the row it left out now counts
            # as dropped: that item opens as the balance break closes.
            assert (
                "Review  1 dropped-transaction opened; 1 balance-break closed"
            ) in stdout


if __name__ == "__main__":
    unittest.main()
