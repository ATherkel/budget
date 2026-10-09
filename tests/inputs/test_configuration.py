# Copyright 2026 Therkel
"""`taxonomy.toml` and `rules.toml`, through `load_configuration`.

Every file here is synthetic and written into a test profile's own inputs
folder. The examples `operations.md` documents are read from that document, so
an example that stops loading fails here.
"""

import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from budget.inputs import (
    AssignAdjustment,
    AssignCategory,
    Category,
    CategoryGroup,
    ClaimTransfer,
    ConfigurationSnapshot,
    Rule,
    RuleConditions,
    load_configuration,
)
from budget.profiles import test_profile as make_test_profile

OPERATIONS = (
    Path(__file__).resolve().parents[2] / "docs" / "architecture" / "operations.md"
)


def documented_example(file_name: str) -> str:
    """The TOML example under `operations.md`'s heading for the file."""
    text = OPERATIONS.read_text(encoding="utf-8")
    _, _, section = text.partition(f"### `{file_name}`\n")
    _, _, block = section.partition("```toml\n")
    example, _, _ = block.partition("```")
    assert example, f"operations.md has no {file_name} example"
    return example


ACCOUNTS = documented_example("accounts.toml")
TAXONOMY = documented_example("taxonomy.toml")
RULES = documented_example("rules.toml")


def configuration(
    accounts: str = ACCOUNTS, taxonomy: str = TAXONOMY, rules: str = RULES
) -> ConfigurationSnapshot:
    """Load the given files through a throwaway test profile."""
    with TemporaryDirectory() as directory:
        profile = make_test_profile(directory)
        profile.inputs.mkdir(parents=True)
        for name, content in (
            ("accounts.toml", accounts),
            ("taxonomy.toml", taxonomy),
            ("rules.toml", rules),
        ):
            profile.input_file(name).write_text(content, encoding="utf-8")
        return load_configuration(profile)


class DocumentedExamplesTests(unittest.TestCase):
    def test_the_documented_examples_load(self) -> None:
        snapshot = configuration()

        assert list(snapshot.accounts) == ["joint-current", "joint-savings"]
        assert dict(snapshot.taxonomy.groups) == {
            "food": CategoryGroup("food", "Food", "expense"),
            "home": CategoryGroup("home", "Home", "expense"),
        }
        assert dict(snapshot.taxonomy.categories) == {
            "groceries": Category("groceries", "Groceries", "food"),
            "eating-out": Category("eating-out", "Eating out", "food"),
            "furniture": Category("furniture", "Furniture", "home"),
        }
        assert dict(snapshot.rules) == {
            "r-netto": Rule(
                "r-netto",
                0,
                RuleConditions(description_contains=("NETTO",)),
                AssignCategory("groceries"),
            ),
            "r-furniture": Rule(
                "r-furniture",
                10,
                RuleConditions(
                    description_contains=("IKEA",), amount_max=Decimal("-1000.00")
                ),
                AssignCategory("furniture"),
            ),
            "r-savings-transfer": Rule(
                "r-savings-transfer",
                0,
                RuleConditions(description_contains=("TO SAVINGS", "FROM CURRENT")),
                ClaimTransfer(),
            ),
            "r-bank-groceries": Rule(
                "r-bank-groceries",
                -10,
                RuleConditions(bank_category="Groceries"),
                AssignCategory("groceries"),
            ),
            "r-interest-correction": Rule(
                "r-interest-correction",
                0,
                RuleConditions(
                    account="joint-savings", description_starts_with=("RENTEKORR",)
                ),
                AssignAdjustment("Bank's interest correction"),
            ),
        }


if __name__ == "__main__":
    unittest.main()
