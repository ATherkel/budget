# Copyright 2026 Therkel
"""`budget decide`: propose a decision to the boundary, then rebuild.

Every test drives `main` on a synthetic household whose Silver holds one
unclassified outflow of 45.00 DKK (`tests.cli.pipelines`), as walkthrough W2
in `operations.md` settles a review item. What was recorded is read back from
`decisions.jsonl`, and what was published through `GoldStore`.
"""

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.rebuilding import rebuild_from_silver
from budget.silver.store import SilverStore
from tests.cli.commands import decide, rebuild
from tests.cli.pipelines import household, prepared
from tests.importing.households import (
    chained_payload,
    drop,
    incoming_payload,
    payload,
)

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3


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


def decided(profile_file: Path, *arguments: str) -> None:
    """Run `budget decide` and require it to record and publish."""
    status, _, stderr = decide(profile_file, *arguments)
    assert (status, stderr) == (EXIT_OK, "")


def fields(entry: dict[str, object]) -> dict[str, object]:
    """An entry without the fields the platform sets."""
    return {
        key: value
        for key, value in entry.items()
        if key not in {"format", "entry", "decision_id", "recorded_at"}
    }


class GrammarTests(unittest.TestCase):
    """Each kind's command line records the entry `operations.md` documents."""

    def test_a_pair_names_two_handles_and_a_retract_only_what_it_supersedes(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = prepared(Path(directory))
            profile = built.profile
            march = Coverage(
                covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)
            )
            with writer_lock(profile) as lock:
                for account_id, export in (
                    ("joint-current", payload("01.03.2026")),
                    ("joint-savings", incoming_payload("01.03.2026")),
                ):
                    source = drop(profile, account_id, "danske-20260305.csv", export)
                    import_inbox_file(lock, source, march)
                rebuild_from_silver(lock)
            with SilverStore(profile) as silver:
                by_account = {
                    t.account_id: t.transaction_id for t in silver.read().transactions
                }
            out, into = by_account["joint-current"], by_account["joint-savings"]

            decided(built.profile_file, "pair", out[:8], into[:8], "--reason", "Moved")
            decided(
                built.profile_file,
                "retract",
                "--supersedes",
                "d-0001",
                "--reason",
                "Not a transfer",
            )

            assert [fields(entry) for entry in log_lines(profile)] == [
                {
                    "kind": "pair",
                    "targets": [out, into],
                    "reason": "Moved",
                    "supersedes": [],
                },
                {
                    "kind": "retract",
                    "targets": [],
                    "reason": "Not a transfer",
                    "supersedes": ["d-0001"],
                },
            ]

    def test_an_adjustment_and_a_one_sided_transfer_take_their_options(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            transaction_id = only_transaction(built.profile)
            handle = transaction_id[:8]

            decided(
                built.profile_file,
                "classify",
                handle,
                "--adjustment",
                "--reason",
                "Bank correction",
            )
            decided(
                built.profile_file,
                "one-sided-transfer",
                handle,
                "--counterpart",
                "joint-savings",
                "--supersedes",
                "d-0001",
                "--reason",
                "To savings",
            )

            assert [fields(entry) for entry in log_lines(built.profile)] == [
                {
                    "kind": "classify",
                    "targets": [transaction_id],
                    "adjustment": True,
                    "reason": "Bank correction",
                    "supersedes": [],
                },
                {
                    "kind": "one-sided-transfer",
                    "targets": [transaction_id],
                    "counterpart_account_id": "joint-savings",
                    "reason": "To savings",
                    "supersedes": ["d-0001"],
                },
            ]


class RejectionTests(unittest.TestCase):
    def test_a_rejected_decision_exits_3_naming_its_reasons_and_records_nothing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            assert rebuild(built.profile_file)[0] == EXIT_OK
            transaction_id = only_transaction(built.profile)

            status, stdout, stderr = decide(
                built.profile_file,
                "classify",
                transaction_id[:8],
                "eating-out",
                "--reason",
                "Synthetic",
            )

            assert (status, stdout) == (EXIT_REFUSED_INPUT, "")
            assert stderr == (
                "budget: the decision was rejected; nothing was recorded:\n"
                '  category "eating-out" is not in the taxonomy\n'
            )
            assert not built.profile.input_file("decisions.jsonl").exists()
            with GoldStore(built.profile) as gold:
                assert [m.to_publication_id for m in gold.pointer_history()] == [1]

    def test_a_handle_that_names_no_single_transaction_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            built = prepared(Path(directory))
            profile = built.profile
            march = Coverage(
                covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)
            )
            export = chained_payload("01.03.2026", "02.03.2026")
            with writer_lock(profile) as lock:
                source = drop(profile, "joint-current", "danske-20260305.csv", export)
                import_inbox_file(lock, source, march)
                rebuild_from_silver(lock)
            with SilverStore(profile) as silver:
                ids = sorted(t.transaction_id for t in silver.read().transactions)
            # Every transaction ID starts with the empty handle.
            refusals = {
                "zzzzzzzz": 'no transaction in Silver has the handle "zzzzzzzz"',
                "": (
                    'the handle "" matches more than one transaction '
                    f"({ids[0][:12]}…, {ids[1][:12]}…); type more of its ID"
                ),
            }
            for handle, reason in refusals.items():
                with self.subTest(handle=handle):
                    status, _, stderr = decide(
                        built.profile_file,
                        "classify",
                        handle,
                        "groceries",
                        "--reason",
                        "Synthetic",
                    )

                    assert status == EXIT_REFUSED_INPUT
                    assert stderr == (
                        "budget: the decision was rejected; nothing was recorded:\n"
                        f"  {reason}\n"
                    )
            assert not profile.input_file("decisions.jsonl").exists()
