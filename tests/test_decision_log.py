# Copyright 2026 Therkel
"""`decisions.jsonl`, through `read_decision_log`.

Every log here is synthetic and written into a test profile's own inputs
folder. The example `operations.md` documents is read from that document, so
an example that stops reading as described fails here.
"""

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from budget.decision_log import DecisionLogRead, read_decision_log
from budget.gold.decisions import Classify, ClassifyAdjustment, OneSidedTransfer, Pair
from budget.inputs import ConfigurationError
from budget.profiles import test_profile as make_test_profile
from budget.silver.decisions import (
    AcceptDiscrepancy,
    SameTransaction,
    VoidImportRun,
    Withdrawn,
)

OPERATIONS = (
    Path(__file__).resolve().parents[1] / "docs" / "architecture" / "operations.md"
)


def documented_example() -> str:
    """The JSON Lines example under `operations.md`'s decision-log heading."""
    text = OPERATIONS.read_text(encoding="utf-8")
    _, _, section = text.partition("### `decisions.jsonl`: the decision log\n")
    _, _, block = section.partition("```json\n")
    example, _, _ = block.partition("```")
    assert example, "operations.md has no decisions.jsonl example"
    return example


def read_log(content: bytes) -> DecisionLogRead:
    """Read `content` as the decision log of a throwaway test profile."""
    with TemporaryDirectory() as directory:
        profile = make_test_profile(directory)
        profile.inputs.mkdir(parents=True)
        profile.input_file("decisions.jsonl").write_bytes(content)
        return read_decision_log(profile)


class DocumentedExampleTests(unittest.TestCase):
    def test_the_retract_leaves_only_the_pair_in_force(self) -> None:
        read = read_log(documented_example().encode())

        assert read.gold == (Pair("d-0002", ("3f9a2c1e77b0…", "a04d6e12c9f3…")),)
        assert read.silver == ()
        assert read.position == 3


def classify(entry: int, target: str, category: str, *supersedes: str) -> str:
    """One complete `classify` line, numbered `entry`, with its line feed."""
    fields = {
        "format": 1,
        "entry": entry,
        "decision_id": f"d-{entry:04d}",
        "recorded_at": f"2026-04-{entry:02d}T12:00:00Z",
        "kind": "classify",
        "targets": [target],
        "category": category,
        "reason": "Synthetic",
        "supersedes": list(supersedes),
    }
    return json.dumps(fields) + "\n"


def refusal(content: bytes) -> tuple[str, ...]:
    """The problems reading `content` as the decision log refuses with."""
    with pytest.raises(ConfigurationError) as refused:
        read_log(content)
    return refused.value.problems


class SupersessionTests(unittest.TestCase):
    def test_a_second_decision_on_a_target_must_supersede_the_first(self) -> None:
        log = classify(1, "tx-a", "gifts") + classify(2, "tx-a", "groceries")

        assert refusal(log.encode()) == (
            (
                "decisions.jsonl: entry 2 (d-0002): tx-a is already decided by "
                "d-0001, which supersedes does not list"
            ),
        )

    def test_a_retract_frees_its_target_for_a_new_decision(self) -> None:
        log = (
            classify(1, "tx-a", "gifts")
            + decision(2, "retract", [], supersedes=["d-0001"])
            + classify(3, "tx-a", "groceries")
        )

        assert read_log(log.encode()).gold == (Classify("d-0003", "tx-a", "groceries"),)

    def test_an_invalid_entry_never_holds_its_target(self) -> None:
        log = line(1, targets=["tx-a"], format=2) + classify(2, "tx-a", "groceries")

        assert refusal(log.encode()) == (problem("format must be 1"),)


class PrefixTests(unittest.TestCase):
    def test_an_edited_entry_changes_the_prefix_hash(self) -> None:
        recorded = read_log(classify(1, "tx-a", "gifts").encode())
        edited = read_log(classify(1, "tx-a", "groceries").encode())

        assert recorded.position == edited.position == 1
        assert recorded.prefix_sha256 != edited.prefix_sha256

    def test_the_hash_covers_exactly_the_bytes_read(self) -> None:
        log = classify(1, "tx-a", "gifts").encode()

        assert read_log(log).prefix_sha256 == hashlib.sha256(log).hexdigest()

    def test_a_final_line_without_a_line_feed_was_never_written(self) -> None:
        complete = classify(1, "tx-a", "gifts")
        cut_off = classify(2, "tx-b", "gifts").rstrip("\n")

        read = read_log((complete + cut_off).encode())

        assert read.gold == (Classify("d-0001", "tx-a", "gifts"),)
        assert read.position == 1
        assert read.prefix_sha256 == read_log(complete.encode()).prefix_sha256

    def test_a_missing_log_holds_no_decisions(self) -> None:
        with TemporaryDirectory() as directory:
            read = read_decision_log(make_test_profile(directory))

        assert read == DecisionLogRead(
            silver=(), gold=(), position=0, prefix_sha256=hashlib.sha256().hexdigest()
        )


def line(entry: int = 1, **changes: object) -> str:
    """One complete `classify` line on `tx-a`, with keys changed or dropped.

    A change to `DROP` removes the key.
    """
    fields = json.loads(classify(entry, f"tx-{entry}", "gifts"))
    fields.update(changes)
    kept = {key: value for key, value in fields.items() if value is not DROP}
    return json.dumps(kept) + "\n"


DROP = object()


def problem(text: str, entry: int = 1, decision_id: str | None = "d-0001") -> str:
    """Spell one entry's problem the way the reader reports it."""
    name = f"entry {entry}" if decision_id is None else f"entry {entry} ({decision_id})"
    return f"decisions.jsonl: {name}: {text}"


def decision(entry: int, kind: str, targets: list[str], **fields: object) -> str:
    """One complete line of any kind, numbered `entry`, with only `fields` added."""
    changes = {"category": DROP, **fields}
    return line(entry, kind=kind, targets=targets, **changes)


def held(target: str, by: str) -> str:
    """Spell entry 2's clash with the decision in force on `target`."""
    return problem(
        f"{target} is already decided by {by}, which supersedes does not list",
        2,
        "d-0002",
    )


RECORD_P1 = {"payload_id": "p-1", "record_ordinal": 0}
RECORD_P2 = {"payload_id": "p-2", "record_ordinal": 0}
SHARES_NOTHING = "supersedes d-0001, which decides nothing this entry targets"


INVALID_LOGS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("not JSON", "not json\n", (problem("must be one JSON object", decision_id=None),)),
    ("a blank line", "\n", (problem("must be one JSON object", decision_id=None),)),
    ("an unknown format", line(format=2), (problem("format must be 1"),)),
    (
        "an entry out of position",
        line(entry=3, decision_id="d-0001"),
        (problem("entry must be 1, its position in the log"),),
    ),
    (
        "an unknown kind",
        line(kind="rename"),
        (problem('kind "rename" is not a decision kind'),),
    ),
    ("an unknown key", line(note="x"), (problem('unknown key "note"'),)),
    ("a missing reason", line(reason=DROP), (problem("reason is missing"),)),
    (
        "a classify with two targets",
        line(targets=["tx-a", "tx-b"]),
        (problem("targets must list exactly 1 target"),),
    ),
    (
        "a pair with one target",
        line(kind="pair", targets=["tx-a"], category=DROP),
        (problem("targets must list exactly 2 targets"),),
    ),
    (
        "a local recorded_at",
        line(recorded_at="2026-04-01T12:00:00"),
        (problem("recorded_at must be a UTC time such as 2026-04-10T17:02:11Z"),),
    ),
    (
        "a classify with category and adjustment",
        line(adjustment=True),
        (problem("classify must give exactly one of category or adjustment"),),
    ),
    (
        "a classify with neither",
        line(category=DROP),
        (problem("classify must give exactly one of category or adjustment"),),
    ),
    (
        "a one-sided transfer without a counterpart",
        line(kind="one-sided-transfer", category=DROP),
        (problem("counterpart_account_id is missing"),),
    ),
    (
        "a same-transaction record without its ordinal",
        line(kind="same-transaction", category=DROP, record={"payload_id": "p-1"}),
        (problem("record.record_ordinal is missing"),),
    ),
    (
        "a supersedes naming no decision in force",
        line(supersedes=["d-0009"]),
        (problem("supersedes d-0009, which is not in force"),),
    ),
    (
        "a retract superseding nothing",
        line(kind="retract", targets=[], category=DROP),
        (problem("a retract must supersede a decision"),),
    ),
    (
        "a reused decision_id",
        line(1) + line(2, decision_id="d-0001"),
        (problem("decision_id d-0001 is already used by entry 1", entry=2),),
    ),
    (
        "a supersedes naming one decision twice",
        line(1) + line(2, targets=["tx-1"], supersedes=["d-0001", "d-0001"]),
        (problem("supersedes lists d-0001 more than once", 2, "d-0002"),),
    ),
    (
        "a pair of one transaction with itself",
        line(kind="pair", targets=["tx-a", "tx-a"], category=DROP),
        (problem("targets lists tx-a more than once"),),
    ),
    (
        "a repeated key",
        line(category="gifts")[:-2] + ', "category": "groceries"}\n',
        (problem('key "category" appears more than once'),),
    ),
    (
        "a repeated key inside record",
        decision(1, "same-transaction", ["tx-a"], record=RECORD_P1).replace(
            '"payload_id": "p-1"', '"payload_id": "p-1", "payload_id": "p-2"'
        ),
        (problem('key "record.payload_id" appears more than once'),),
    ),
    (
        "a retract with a target",
        line(1) + decision(2, "retract", ["tx-1"], supersedes=["d-0001"]),
        (problem("a retract has no targets", 2, "d-0002"),),
    ),
    (
        "a second same-transaction for one record's payload",
        decision(1, "same-transaction", ["tx-a"], record=RECORD_P1)
        + decision(2, "same-transaction", ["tx-a"], record=RECORD_P1),
        (held("tx-a", by="d-0001"),),
    ),
    (
        "a same-transaction on a withdrawn transaction",
        decision(1, "withdrawn", ["tx-a"])
        + decision(2, "same-transaction", ["tx-a"], record=RECORD_P1),
        (held("tx-a", by="d-0001"),),
    ),
    (
        "a withdrawn on a transaction with a same-transaction",
        decision(1, "same-transaction", ["tx-a"], record=RECORD_P1)
        + decision(2, "withdrawn", ["tx-a"]),
        (held("tx-a", by="d-0001"),),
    ),
    (
        "an accept-discrepancy on a voided run",
        decision(1, "void-import-run", ["run-1"])
        + decision(2, "accept-discrepancy", ["run-1"]),
        (held("run-1", by="d-0001"),),
    ),
    (
        "a one-sided transfer on a paired leg",
        decision(1, "pair", ["tx-a", "tx-b"])
        + decision(
            2, "one-sided-transfer", ["tx-b"], counterpart_account_id="joint-savings"
        ),
        (held("tx-b", by="d-0001"),),
    ),
    (
        "a supersedes naming a decision on another target",
        classify(1, "tx-a", "gifts") + classify(2, "tx-b", "gifts", "d-0001"),
        (problem(SHARES_NOTHING, 2, "d-0002"),),
    ),
    (
        "a Silver decision superseding a Gold one",
        classify(1, "tx-a", "gifts")
        + decision(
            2, "same-transaction", ["tx-a"], record=RECORD_P1, supersedes=["d-0001"]
        ),
        (problem(SHARES_NOTHING, 2, "d-0002"),),
    ),
)


class EntryValidationTests(unittest.TestCase):
    def test_each_invalid_entry_is_refused_naming_its_problem(self) -> None:
        for case, log, expected in INVALID_LOGS:
            with self.subTest(case):
                assert refusal(log.encode()) == expected


class CollisionTests(unittest.TestCase):
    def test_silver_and_gold_decisions_on_one_transaction_both_hold(self) -> None:
        log = (
            classify(1, "tx-a", "gifts")
            + decision(2, "same-transaction", ["tx-a"], record=RECORD_P1)
            + decision(3, "same-transaction", ["tx-a"], record=RECORD_P2)
        )

        read = read_log(log.encode())

        assert read.gold == (Classify("d-0001", "tx-a", "gifts"),)
        assert read.silver == (
            SameTransaction("d-0002", "tx-a", "p-1", 0),
            SameTransaction("d-0003", "tx-a", "p-2", 0),
        )

    def test_a_withdrawn_transaction_keeps_its_classification(self) -> None:
        log = classify(1, "tx-a", "gifts") + decision(2, "withdrawn", ["tx-a"])

        read = read_log(log.encode())

        assert read.gold == (Classify("d-0001", "tx-a", "gifts"),)
        assert read.silver == (Withdrawn("d-0002", "tx-a"),)


class TypedDecisionTests(unittest.TestCase):
    def test_an_adjustment_decision_carries_its_own_reason(self) -> None:
        log = decision(
            1, "classify", ["tx-a"], adjustment=True, reason="Opening balance fix"
        )

        read = read_log(log.encode())

        assert read.gold == (
            ClassifyAdjustment("d-0001", "tx-a", "Opening balance fix"),
        )

    def test_each_kind_in_force_reads_as_its_typed_decision(self) -> None:
        log = (
            decision(1, "classify", ["tx-a"], category="gifts")
            + decision(2, "classify", ["tx-b"], adjustment=True)
            + decision(3, "pair", ["tx-c", "tx-d"])
            + decision(
                4,
                "one-sided-transfer",
                ["tx-e"],
                counterpart_account_id="joint-savings",
            )
            + decision(5, "void-import-run", ["run-1"])
            + decision(6, "accept-discrepancy", ["run-2"])
            + decision(7, "withdrawn", ["tx-f"])
            + decision(
                8,
                "same-transaction",
                ["tx-g"],
                record={"payload_id": "p-1", "record_ordinal": 4},
            )
        )

        read = read_log(log.encode())

        assert read.gold == (
            Classify("d-0001", "tx-a", "gifts"),
            ClassifyAdjustment("d-0002", "tx-b", "Synthetic"),
            Pair("d-0003", ("tx-c", "tx-d")),
            OneSidedTransfer("d-0004", "tx-e", "joint-savings"),
        )
        assert read.silver == (
            VoidImportRun("d-0005", "run-1"),
            AcceptDiscrepancy("d-0006", "run-2"),
            Withdrawn("d-0007", "tx-f"),
            SameTransaction("d-0008", "tx-g", "p-1", 4),
        )

    def test_a_superseding_pair_replaces_both_legs_classify(self) -> None:
        log = (
            classify(1, "tx-a", "gifts")
            + classify(2, "tx-b", "gifts")
            + decision(3, "pair", ["tx-a", "tx-b"], supersedes=["d-0001", "d-0002"])
        )

        assert read_log(log.encode()).gold == (Pair("d-0003", ("tx-a", "tx-b")),)


class EncodingTests(unittest.TestCase):
    def test_a_log_that_is_not_utf8_is_refused(self) -> None:
        log = classify(1, "tx-a", "gifts").encode() + b"\xff\n"

        assert refusal(log) == ("decisions.jsonl: the file is not UTF-8",)
