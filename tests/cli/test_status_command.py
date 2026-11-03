# Copyright 2026 Therkel
"""`budget status`: balance and classification completeness, read-only.

Every profile and result is synthetic. The seam is the CLI itself, so these
tests observe what an operator reads, not the report objects behind it.
"""

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold import GoldRecords, GoldResult, MonthlyBalanceSnapshot, ReportingMonth
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from tests.cli.commands import status
from tests.cli.profile_files import development_profile, write_profile
from tests.gold.publishing import CONFIGURATION, RECIPE, publication, publish
from tests.gold.worked_example import ACCOUNTS, CURRENT

EXIT_OK = 0
# The day after the worked example's only export, so May is its current month.
PUBLISHED_AT = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
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

    def test_status_names_the_publication_and_each_account_months_coverage(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                publish(store, 1)

            code, stdout, stderr = status(profile_file, now=PUBLISHED_AT)

            lines = stdout.splitlines()
            assert (code, stderr) == (EXIT_OK, "")
            assert "Published figures: publication 1 (current)" in lines
            assert [line for line in lines if line.startswith("joint-")] == [
                "joint-current  2026-01  partial",
                "joint-current  2026-02  partial",
                "joint-current  2026-03  partial",
                "joint-current  2026-04  complete",
                "joint-current  2026-05  partial",
                "joint-savings  2026-01  partial",
                "joint-savings  2026-02  complete",
                "joint-savings  2026-03  complete",
                "joint-savings  2026-04  complete",
                "joint-savings  2026-05  partial",
            ]

    def test_status_shows_only_the_latest_twelve_months_of_a_longer_history(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                store.publish(
                    GoldResult(publication(1), _fourteen_months()),
                    RECIPE,
                    CONFIGURATION,
                )

            code, stdout, stderr = status(
                profile_file, now=datetime(2026, 4, 20, tzinfo=UTC)
            )

            months = [
                line.split("  ")[1]
                for line in stdout.splitlines()
                if line.startswith("joint-current")
            ]
            assert (code, stderr) == (EXIT_OK, "")
            assert months == [
                "2025-05",
                "2025-06",
                "2025-07",
                "2025-08",
                "2025-09",
                "2025-10",
                "2025-11",
                "2025-12",
                "2026-01",
                "2026-02",
                "2026-03",
                "2026-04",
            ]


def _fourteen_months() -> GoldRecords:
    """One account with a complete snapshot for each month, March 2025 to April 2026."""
    snapshots = tuple(
        MonthlyBalanceSnapshot(
            account_id=CURRENT,
            month=ReportingMonth(2025 + (index + 2) // 12, (index + 2) % 12 + 1),
            opening_balance=None,
            closing_balance=None,
            coverage="complete",
            late_bookings_settled=True,
        )
        for index in range(14)
    )
    return GoldRecords(accounts=ACCOUNTS[:1], monthly_balances=snapshots)


if __name__ == "__main__":
    unittest.main()
