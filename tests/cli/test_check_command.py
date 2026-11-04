# Copyright 2026 Therkel
"""`budget check`: validate every input and the decision-log prefix, read-only.

Every profile, input and decision is synthetic. The seam is the CLI itself,
so these tests observe what an operator reads and the exit status.
"""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.profiles import Profile
from tests.cli.commands import check
from tests.cli.pipelines import write_inputs
from tests.cli.profile_files import development_profile, write_profile

EXIT_OK = 0
EXIT_REFUSED_INPUT = 3

TAXONOMY_WITH_AN_UNDECLARED_GROUP = """\
format = 1

[group.food]
name = "Food"
direction = "expense"

[category.groceries]
name = "Groceries"
group = "drink"
"""
# A rule written as a table, not as one `[[rule]]` block per rule.
RULES_AS_A_TABLE = """\
format = 1

[rule.r-netto]
priority = 10
"""
# Well-formed, but `furniture` is in no taxonomy this file's tests write.
RULES_NAMING_AN_UNKNOWN_CATEGORY = """\
format = 1

[[rule]]
id = "r-ikea"
when = { description_contains = "IKEA" }
then = { category = "furniture" }
"""


def _everything_under(folder: Path) -> list[str]:
    """Every path under `folder`, relative to it, in order."""
    return sorted(str(path.relative_to(folder)) for path in folder.rglob("*"))


def _write(profile: Profile, name: str, text: str) -> None:
    """Replace one input file of `profile` with `text`."""
    profile.input_file(name).write_text(text, encoding="utf-8")


def _entry(position: int, kind: str, targets: list[str], **fields: object) -> str:
    """One well-formed `decisions.jsonl` line, `d-000<position>`, at `position`."""
    entry = {
        "format": 1,
        "entry": position,
        "decision_id": f"d-{position:04}",
        "recorded_at": "2026-04-10T17:02:11Z",
        "kind": kind,
        "targets": targets,
        "reason": "synthetic",
        "supersedes": [],
        **fields,
    }
    return json.dumps(entry) + "\n"


class CheckCommandTests(unittest.TestCase):
    def test_valid_inputs_without_a_gold_store_pass_and_create_nothing(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            write_inputs(development_profile(folder))
            before = _everything_under(folder)

            code, stdout, stderr = check(profile_file)

            assert (code, stdout, stderr) == (EXIT_OK, "No problems found.\n", "")
            assert _everything_under(folder) == before

    def test_problems_in_two_files_and_the_log_are_all_listed_then_refused(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            write_inputs(profile)
            _write(profile, "taxonomy.toml", TAXONOMY_WITH_AN_UNDECLARED_GROUP)
            _write(profile, "rules.toml", RULES_AS_A_TABLE)
            _write(profile, "decisions.jsonl", "not json\n")

            code, stdout, stderr = check(profile_file)

            assert (code, stderr) == (EXIT_REFUSED_INPUT, "")
            assert stdout.splitlines() == [
                'taxonomy.toml: category "groceries": group "drink" is not declared',
                "rules.toml: rule must hold one [[rule]] block per rule",
                "decisions.jsonl: entry 1: must be one JSON object",
                "3 problems. Nothing was built.",
            ]

    def test_a_classify_decision_naming_a_category_the_taxonomy_lacks_is_listed(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            write_inputs(profile)
            log = _entry(1, "classify", ["t-netto"], category="groceries")
            log += _entry(2, "classify", ["t-ikea"], category="furniture")
            _write(profile, "decisions.jsonl", log)

            code, stdout, stderr = check(profile_file)

            assert (code, stderr) == (EXIT_REFUSED_INPUT, "")
            assert stdout.splitlines() == [
                'decisions.jsonl: decision "d-0002": category "furniture" is not '
                "in the taxonomy; record a decision that supersedes it",
                "1 problem. Nothing was built.",
            ]
    def test_decisions_are_judged_against_the_accounts_while_rules_are_refused(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            write_inputs(profile)
            _write(profile, "rules.toml", RULES_AS_A_TABLE)
            log = _entry(
                1, "one-sided-transfer", ["t-to-bo"], counterpart_account_id="bo-current"
            )
            _write(profile, "decisions.jsonl", log)

            code, stdout, stderr = check(profile_file)

            assert (code, stderr) == (EXIT_REFUSED_INPUT, "")
            assert stdout.splitlines() == [
                "rules.toml: rule must hold one [[rule]] block per rule",
                'decisions.jsonl: decision "d-0001": counterpart account '
                '"bo-current" is not in accounts.toml; record a decision that '
                "supersedes it",
                "2 problems. Nothing was built.",
            ]
    def test_a_refused_taxonomy_suppresses_every_category_check_but_no_other(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            profile_file = write_profile(folder)
            profile = development_profile(folder)
            write_inputs(profile)
            _write(profile, "taxonomy.toml", TAXONOMY_WITH_AN_UNDECLARED_GROUP)
            _write(profile, "rules.toml", RULES_NAMING_AN_UNKNOWN_CATEGORY)
            log = _entry(1, "classify", ["t-ikea"], category="furniture")
            log += _entry(
                2, "one-sided-transfer", ["t-to-bo"], counterpart_account_id="bo-current"
            )
            _write(profile, "decisions.jsonl", log)

            code, stdout, stderr = check(profile_file)

            assert (code, stderr) == (EXIT_REFUSED_INPUT, "")
            assert stdout.splitlines() == [
                'taxonomy.toml: category "groceries": group "drink" is not declared',
                'decisions.jsonl: decision "d-0002": counterpart account '
                '"bo-current" is not in accounts.toml; record a decision that '
                "supersedes it",
                "2 problems. Nothing was built.",
            ]