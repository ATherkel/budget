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
from budget.gold.decisions import Classify, Pair
from budget.inputs import ConfigurationError
from budget.profiles import test_profile as make_test_profile

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
