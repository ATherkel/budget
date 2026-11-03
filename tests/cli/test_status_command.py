# Copyright 2026 Therkel
"""`budget status`: balance and classification completeness, read-only.

Every profile and result is synthetic. The seam is the CLI itself, so these
tests observe what an operator reads, not the report objects behind it.
"""

import unittest
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold import (
    GoldRecords,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.locking import writer_lock
from tests.cli.commands import status
from tests.cli.profile_files import development_profile, write_profile
from tests.gold.publishing import CONFIGURATION, RECIPE, publication, publish
from tests.gold.worked_example import ACCOUNTS, CURRENT, RECORDS

EXIT_OK = 0
# The day after the worked example's only export, so May is its current month.
PUBLISHED_AT = datetime(2026, 5, 9, 8, 0, tzinfo=UTC)
MAY_PROVISIONAL = "  provisional: current month, late bookings unsettled"
NOTHING_PUBLISHED = "Published figures: unavailable, nothing is published"


def _everything_under(folder: Path, *, without_sidecars: bool = False) -> list[str]:
    """Every path under `folder`, relative to it, in order.

    `without_sidecars` leaves out SQLite's own `-wal` and `-shm` files: any
    read-only connection to a WAL store opens them, as `review` and `serve` do.
    """
    return sorted(
        str(path.relative_to(folder))
        for path in folder.rglob("*")
        if not (without_sidecars and path.name.endswith(("-wal", "-shm")))
    )


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
                f"joint-current  2026-05  partial{MAY_PROVISIONAL}",
                "joint-savings  2026-01  partial",
                "joint-savings  2026-02  complete",
                "joint-savings  2026-03  complete",
                "joint-savings  2026-04  complete",
                f"joint-savings  2026-05  partial{MAY_PROVISIONAL}",
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


class StatusProvisionalTests(unittest.TestCase):
    def test_status_says_why_a_month_is_provisional(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                publish(store, 1)

            _, in_may, _ = status(profile_file, now=PUBLISHED_AT)
            _, in_june, _ = status(profile_file, now=datetime(2026, 6, 10, tzinfo=UTC))

            def lines(output: str, month: str) -> list[str]:
                return [
                    line
                    for line in output.splitlines()
                    if line.startswith("joint-current") and f"  {month}  " in line
                ]

            assert lines(in_may, "2026-04") == ["joint-current  2026-04  complete"]
            assert lines(in_may, "2026-05") == [
                (
                    "joint-current  2026-05  partial"
                    "  provisional: current month, late bookings unsettled"
                )
            ]
            assert lines(in_june, "2026-05") == [
                "joint-current  2026-05  partial  provisional: late bookings unsettled"
            ]


class StatusClassificationTests(unittest.TestCase):
    def test_status_shows_unclassified_money_in_and_out_without_netting(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                store.publish(
                    GoldResult(publication(1), _with_a_second_unknown_in_march()),
                    RECIPE,
                    CONFIGURATION,
                )

            code, stdout, stderr = status(profile_file, now=PUBLISHED_AT)

            lines = stdout.splitlines()
            assert (code, stderr) == (EXIT_OK, "")
            assert "Unclassified money, by account and month" in lines
            by_month = {
                line.split("  ")[2]: line
                for line in lines
                if line.startswith("  joint-current  ")
            }
            assert by_month["2026-03"] == (
                "  joint-current  2026-03"
                "  in 200.00 DKK, out -450.00 DKK, 2 transactions"
            )
            assert by_month["2026-04"] == (
                "  joint-current  2026-04  in 0.00 DKK, out 0.00 DKK, 0 transactions"
            )

    def test_status_marks_a_month_without_data_unavailable_not_zero(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                publish(store, 1)

            _, stdout, _ = status(profile_file, now=datetime(2026, 6, 10, tzinfo=UTC))

            lines = stdout.splitlines()
            assert (
                "joint-current  2026-06  no data"
                "  provisional: current month, late bookings unsettled"
            ) in lines
            assert "  joint-current  2026-06  unavailable: no data" in lines

    def test_status_says_one_transaction_in_the_singular(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                publish(store, 1)

            _, stdout, _ = status(profile_file, now=PUBLISHED_AT)

            assert (
                "  joint-current  2026-03  in 0.00 DKK, out -450.00 DKK, 1 transaction"
            ) in stdout.splitlines()


class StatusReadOnlyTests(unittest.TestCase):
    def test_status_runs_beside_a_writer_and_changes_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            migrate_gold(profile)
            with GoldStore(profile) as store:
                publish(store, 1)
            gold_before = profile.gold_store.read_bytes()

            with writer_lock(profile):
                before = _everything_under(folder, without_sidecars=True)
                code, _, stderr = status(profile_file, now=PUBLISHED_AT)
                after = _everything_under(folder, without_sidecars=True)

            wal = profile.gold_store.with_name("gold.db-wal")
            assert (code, stderr) == (EXIT_OK, "")
            assert profile.gold_store.read_bytes() == gold_before
            assert after == before
            # A read-only reader leaves the log empty; any data in it is a write.
            assert not wal.exists() or wal.stat().st_size == 0


def _with_a_second_unknown_in_march() -> GoldRecords:
    """The worked example plus an unknown inflow beside March's unknown outflow."""
    inflow = GoldTransaction(
        transaction_id="current-12",
        account_id=CURRENT,
        transaction_date=date(2026, 3, 15),
        account_sequence=12,
        amount=Decimal("200.00"),
        description="UNKNOWN",
        transaction_type="unknown",
        transfer_group_id=None,
        balance_after=None,
        balance_check="consistent",
    )
    return replace(RECORDS, transactions=(*RECORDS.transactions, inflow))


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
