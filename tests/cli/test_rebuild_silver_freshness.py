# Copyright 2026 Therkel
"""A Silver decision must reach the next Gold publication after its rebuild.

A later export drops one admitted transaction. Gold refuses to publish from the
quarantined Silver, then the decision-led Silver rebuild publishes the corrected
result.
"""

import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from budget.silver import SilverStore
from tests.cli.commands import rebuild
from tests.cli.lifecycle import (
    FEBRUARY,
    RUN_1_ROWS,
    import_export,
    lifecycle,
    transaction_id,
)

EXIT_OK = 0
EXIT_REFUSED_ENVIRONMENT = 4
DECISION_LOG = "decisions.jsonl"


def _withdraw_transaction(transaction_id: str) -> str:
    """Return one documented `withdrawn` decision entry."""
    return (
        json.dumps(
            {
                "format": 1,
                "entry": 1,
                "decision_id": "d-0001",
                "recorded_at": "2026-04-10T17:02:11Z",
                "kind": "withdrawn",
                "targets": [transaction_id],
                "reason": "The bank removed the transaction",
                "supersedes": [],
            }
        )
        + "\n"
    )


class RebuildSilverFreshnessTests(unittest.TestCase):
    def test_default_rebuild_refuses_stale_silver_then_recovers_gold(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            household = lifecycle(Path(directory))
            assert rebuild(household.profile_file)[0] == EXIT_OK
            with GoldStore(household.profile) as gold:
                initial = gold.current()
                assert initial is not None
                initial_history = gold.pointer_history()
                assert (
                    len(
                        gold.open(initial.publication_id).transactions(
                            start_date=FEBRUARY[0], end_date=FEBRUARY[1]
                        )
                    )
                    == 4
                )
            dropped_id = transaction_id(household.profile, "NETFLIX.COM")
            import_export(
                household.profile,
                "danske-20260310.csv",
                RUN_1_ROWS[:3],
                date(2026, 3, 9),
            )
            with SilverStore(household.profile) as silver:
                pending = silver.read()
            assert sorted(run.status for run in pending.import_run_results) == [
                "accepted",
                "quarantined",
            ]
            (dropped,) = [
                item
                for item in pending.review_items
                if item.kind == "dropped-transaction"
            ]
            assert (dropped.transaction_id, dropped.resolved_by) == (dropped_id, None)

            household.profile.input_file(DECISION_LOG).write_text(
                _withdraw_transaction(dropped_id), encoding="utf-8"
            )
            status, stdout, stderr = rebuild(household.profile_file)

            assert (status, stdout) == (EXIT_REFUSED_ENVIRONMENT, "")
            assert "rebuild --from silver" in stderr
            with GoldStore(household.profile) as gold:
                assert gold.pointer_history() == initial_history
                assert gold.current() == initial

            status, stdout, stderr = rebuild(household.profile_file, "--from", "silver")

            assert (status, stderr) == (EXIT_OK, "")
            assert "published publication 2" in stdout
            with SilverStore(household.profile) as silver:
                corrected = silver.read()
            assert [
                (
                    transaction.description,
                    transaction.amount,
                    transaction.balance,
                )
                for transaction in corrected.transactions
            ] == [
                ("NETTO 0412", Decimal("-640.00"), Decimal("9360.00")),
                ("IKEA 551", Decimal("-2400.00"), Decimal("6960.00")),
                ("NETTO 0412", Decimal("120.00"), Decimal("7080.00")),
            ]
            with GoldStore(household.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 2
                assert [
                    (
                        transaction.description,
                        transaction.amount,
                        transaction.balance_after,
                    )
                    for transaction in gold.open(current.publication_id).transactions(
                        start_date=FEBRUARY[0], end_date=FEBRUARY[1]
                    )
                ] == [
                    ("NETTO 0412", Decimal("-640.00"), Decimal("9360.00")),
                    ("IKEA 551", Decimal("-2400.00"), Decimal("6960.00")),
                    ("NETTO 0412", Decimal("120.00"), Decimal("7080.00")),
                ]
                history = gold.pointer_history()

            status, stdout, stderr = rebuild(household.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            with GoldStore(household.profile) as gold:
                assert gold.pointer_history() == history


if __name__ == "__main__":
    unittest.main()
