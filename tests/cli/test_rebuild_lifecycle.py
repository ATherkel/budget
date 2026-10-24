# Copyright 2026 Therkel
"""`budget rebuild` through the lifecycle of `publications.md`, step by step.

The household's exports and inputs are `tests/cli/lifecycle.py`; each change
the lifecycle names is made as the household would make it, and the
publication it gives is read back through `GoldStore`.
"""

import json
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from tests.cli.commands import rebuild
from tests.cli.lifecycle import (
    february_by_category,
    import_run_2,
    lifecycle,
    transaction_id,
)

EXIT_OK = 0
CORRECTION = {
    "format": 1,
    "entry": 1,
    "decision_id": "d-0001",
    "recorded_at": "2026-04-10T17:02:11Z",
    "kind": "classify",
    "category": "gifts",
    "reason": "A present, not furniture",
    "supersedes": [],
}


class CategoryCorrectionTests(unittest.TestCase):
    def test_a_category_correction_publishes_the_lifecycles_third_publication(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            household = lifecycle(Path(directory))
            assert rebuild(household.profile_file)[0] == EXIT_OK
            import_run_2(household.profile)
            assert rebuild(household.profile_file)[0] == EXIT_OK
            entry = {
                **CORRECTION,
                "targets": [transaction_id(household.profile, "IKEA 551")],
            }
            household.profile.input_file("decisions.jsonl").write_text(
                json.dumps(entry) + "\n", encoding="utf-8"
            )

            status, stdout, stderr = rebuild(household.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "publication 3" in stdout
            with GoldStore(household.profile) as gold:
                current = gold.current()
                assert current is not None
                assert current.publication_id == 3
                assert gold.recipe(3).decision_log_position == 1
                assert february_by_category(gold.open(3)) == {
                    "groceries": Decimal("-820.00"),
                    "gifts": Decimal("-2400.00"),
                    "streaming": Decimal("-129.00"),
                }


if __name__ == "__main__":
    unittest.main()
