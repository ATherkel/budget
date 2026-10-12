# Copyright 2026 Therkel
"""`decisions.jsonl`, through `read_decision_log`.

Every log here is synthetic and written into a test profile's own inputs
folder. The example `operations.md` documents is read from that document, so
an example that stops reading as described fails here.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.decision_log import DecisionLogRead, read_decision_log
from budget.gold.decisions import Pair
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
