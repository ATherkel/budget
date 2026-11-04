# Copyright 2026 Therkel
"""The validation boundary for decisions: `DecisionLog.propose`.

Every proposal is made under the profile's writer lock, against a synthetic
household whose Silver is built from one export (`tests.cli.pipelines`). What
was recorded is read back from `decisions.jsonl` itself and through
`read_decision_log`, as the next build reads it.
"""

import json
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.deciding import DecisionLog, DecisionProposal, Recorded, Rejected
from budget.decision_log import read_decision_log
from budget.gold.decisions import Classify
from budget.importing import Coverage, import_inbox_file
from budget.locking import writer_lock
from budget.profiles import Profile
from budget.rebuilding import rebuild_from_silver
from budget.silver.store import SilverStore
from tests.cli.pipelines import household, prepared
from tests.importing.households import drop, payload

RECORDED_AT = datetime(2026, 4, 10, 17, 2, 11, 480000, tzinfo=UTC)


def only_transaction(profile: Profile) -> str:
    """The one transaction the household's Silver holds."""
    with SilverStore(profile) as silver:
        (transaction,) = silver.read().transactions
    return transaction.transaction_id


def log_lines(profile: Profile) -> list[dict[str, object]]:
    """Read every entry of the decision log; each must end with a line feed."""
    text = profile.input_file("decisions.jsonl").read_text(encoding="utf-8")
    assert text.endswith("\n")
    return [json.loads(line) for line in text.splitlines()]


class RecordedTests(unittest.TestCase):
    def test_a_valid_classify_is_recorded_as_the_next_entry(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory)).profile
            transaction_id = only_transaction(profile)

            with writer_lock(profile) as lock:
                result = DecisionLog(lock, clock=lambda: RECORDED_AT).propose(
                    DecisionProposal(
                        kind="classify",
                        targets=(transaction_id,),
                        reason="Weekly shop",
                        details={"category": "groceries"},
                    )
                )

            assert result == Recorded(
                decision_id="d-0001", entry=1, recorded_at="2026-04-10T17:02:11Z"
            )
            assert log_lines(profile) == [
                {
                    "format": 1,
                    "entry": 1,
                    "decision_id": "d-0001",
                    "recorded_at": "2026-04-10T17:02:11Z",
                    "kind": "classify",
                    "targets": [transaction_id],
                    "category": "groceries",
                    "reason": "Weekly shop",
                    "supersedes": [],
                }
            ]
            assert read_decision_log(profile).gold == (
                Classify("d-0001", transaction_id, "groceries"),
            )


def classify(transaction_id: str, category: str, *supersedes: str) -> DecisionProposal:
    """Propose classifying one transaction into `category`."""
    return DecisionProposal(
        kind="classify",
        targets=(transaction_id,),
        reason="Synthetic",
        supersedes=supersedes,
        details={"category": category},
    )


class RejectedTests(unittest.TestCase):
    def test_a_rejection_names_every_reason_and_records_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory)).profile
            transaction_id = only_transaction(profile)
            with writer_lock(profile) as lock:
                log = DecisionLog(lock, clock=lambda: RECORDED_AT)
                log.propose(classify(transaction_id, "groceries"))
                before = profile.input_file("decisions.jsonl").read_bytes()

                result = log.propose(classify(transaction_id, "eating-out"))

            assert isinstance(result, Rejected)
            assert result.reasons == (
                (
                    f"{transaction_id} is already decided by d-0001, "
                    "which supersedes does not list"
                ),
                'category "eating-out" is not in the taxonomy',
            )
            assert profile.input_file("decisions.jsonl").read_bytes() == before

    def test_a_target_that_does_not_exist_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            profile = household(Path(directory)).profile
            transaction_id = only_transaction(profile)
            proposals = {
                "0badc0de is not a transaction in Silver": classify(
                    "0badc0de", "groceries"
                ),
                "run-0404 is not an import run in Bronze": DecisionProposal(
                    kind="void-import-run", targets=("run-0404",), reason="Synthetic"
                ),
                "record nothing:7 is not a source record in Bronze": DecisionProposal(
                    kind="same-transaction",
                    targets=(transaction_id,),
                    reason="Synthetic",
                    details={"record": {"payload_id": "nothing", "record_ordinal": 7}},
                ),
            }
            for reason, proposal in proposals.items():
                with self.subTest(proposal.kind), writer_lock(profile) as lock:
                    result = DecisionLog(lock, clock=lambda: RECORDED_AT).propose(
                        proposal
                    )

                    assert result == Rejected((reason,))
            assert not profile.input_file("decisions.jsonl").exists()

    def test_a_decision_gold_could_not_apply_is_rejected(self) -> None:
        # Two outflows of 45.00, one in each account: no transfer of one
        # into the other.
        with TemporaryDirectory() as directory:
            profile = prepared(Path(directory)).profile
            march = Coverage(
                covers_from=date(2026, 3, 1), covers_through=date(2026, 3, 4)
            )
            with writer_lock(profile) as lock:
                for account_id, dato in (
                    ("joint-current", "01.03.2026"),
                    ("joint-savings", "02.03.2026"),
                ):
                    source = drop(
                        profile, account_id, "danske-20260305.csv", payload(dato)
                    )
                    import_inbox_file(lock, source, march)
                rebuild_from_silver(lock)
            with SilverStore(profile) as silver:
                first, second = (t.transaction_id for t in silver.read().transactions)

            with writer_lock(profile) as lock:
                result = DecisionLog(lock, clock=lambda: RECORDED_AT).propose(
                    DecisionProposal(
                        kind="pair", targets=(first, second), reason="Synthetic"
                    )
                )

            assert result == Rejected(
                (f"the amounts of {first} and {second} do not cancel",)
            )
            assert not profile.input_file("decisions.jsonl").exists()
