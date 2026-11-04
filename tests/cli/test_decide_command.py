# Copyright 2026 Therkel
"""`budget decide`: propose a decision to the boundary, then rebuild.

Every test drives `main` on a synthetic household whose Silver holds one
unclassified outflow of 45.00 DKK (`tests.cli.pipelines`), as walkthrough W2
in `operations.md` settles a review item. What was recorded is read back from
`decisions.jsonl`, and what was published through `GoldStore`.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.profiles import Profile
from budget.silver.store import SilverStore
from tests.cli.commands import decide, rebuild
from tests.cli.pipelines import household

EXIT_OK = 0


def only_transaction(profile: Profile) -> str:
    """The one transaction the household's Silver holds."""
    with SilverStore(profile) as silver:
        (transaction,) = silver.read().transactions
    return transaction.transaction_id


def log_lines(profile: Profile) -> list[dict[str, object]]:
    """Read every entry of the decision log."""
    text = profile.input_file("decisions.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


class WalkthroughTests(unittest.TestCase):
    def test_w2_classifies_a_review_item_by_its_handle_and_publishes(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            transaction_id = only_transaction(built.profile)

            status, stdout, stderr = decide(
                built.profile_file,
                "classify",
                transaction_id[:8],
                "groceries",
                "--reason",
                "Weekly shop",
            )

            assert (status, stderr) == (EXIT_OK, "")
            assert stdout.startswith("Recorded d-0001.\n")
            assert "Gold     published publication 2 (cause build)" in stdout
            assert "unclassified out +45.00 DKK" in stdout
            assert "Published figures: publication 2 (current)" in stdout
            (entry,) = log_lines(built.profile)
            assert (entry["kind"], entry["targets"], entry["category"]) == (
                "classify",
                [transaction_id],
                "groceries",
            )
            assert entry["reason"] == "Weekly shop"
