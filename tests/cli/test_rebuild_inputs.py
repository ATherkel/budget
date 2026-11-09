# Copyright 2026 Therkel
"""`budget rebuild` and the household inputs it fingerprints.

A recipe is compared by what the inputs mean, not by how their files are
written (`publications.md`, *Lifecycle*, step 6).
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.gold.store import GoldStore
from tests.cli.commands import rebuild
from tests.cli.pipelines import household

EXIT_OK = 0
RULES = """\
format = 1

[[rule]]
id = "r-netto"
when.description_contains = "NETTO"
then.category = "groceries"
"""
# The same rule: another comment, another key order, another pattern case.
RULES_REWRITTEN = """\
format = 1

# Groceries, as I like to read them.
[[rule]]
then.category = "groceries"
when.description_contains = "netto"
id = "r-netto"
"""


class SameMeaningTests(unittest.TestCase):
    def test_rules_edited_to_the_same_meaning_publish_nothing(self) -> None:
        with TemporaryDirectory() as directory:
            built = household(Path(directory))
            rules = built.profile.input_file("rules.toml")
            rules.write_text(RULES, encoding="utf-8")
            assert rebuild(built.profile_file)[0] == EXIT_OK
            with GoldStore(built.profile) as gold:
                moves = gold.pointer_history()
            rules.write_text(RULES_REWRITTEN, encoding="utf-8")

            status, stdout, stderr = rebuild(built.profile_file)

            assert (status, stderr) == (EXIT_OK, "")
            assert "nothing was published" in stdout
            with GoldStore(built.profile) as gold:
                assert gold.pointer_history() == moves


if __name__ == "__main__":
    unittest.main()
