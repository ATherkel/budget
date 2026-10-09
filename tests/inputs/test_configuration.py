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

import pytest

from budget.inputs import (
    AssignAdjustment,
    AssignCategory,
    Category,
    CategoryGroup,
    ClaimTransfer,
    ConfigurationError,
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


def refusal(
    accounts: str = ACCOUNTS, taxonomy: str = TAXONOMY, rules: str = RULES
) -> tuple[str, ...]:
    """The problems a configuration error lists for the given files."""
    with pytest.raises(ConfigurationError) as refused:
        configuration(accounts, taxonomy, rules)
    return refused.value.problems


def rule_problem(rule_id: str, text: str) -> str:
    """Spell one rule's problem the way the loader reports it."""
    return f'rules.toml: rule "{rule_id}": {text}'


class RuleProblemTests(unittest.TestCase):
    def test_an_unquoted_amount_is_a_configuration_error(self) -> None:
        for amount in ("-1000.00", "-1000", "-1e3"):
            rules = RULES.replace('"-1000.00"', amount)
            with self.subTest(amount=amount):
                assert refusal(rules=rules) == (
                    rule_problem(
                        "r-furniture",
                        "when.amount_max must be a quoted decimal, got a number",
                    ),
                )

    def test_the_documented_error_examples_give_their_messages(self) -> None:
        # operations.md, *Error reporting*: each problem in file order.
        rules = RULES.replace('"-1000.00"', "-1000.00") + (
            "\n[[rule]]\n"
            'id = "r-mobilepay-netto"\n'
            'when.description_contains = "MOBILEPAY NETTO"\n'
            'then.category = "food-out"\n'
        )

        assert refusal(rules=rules) == (
            rule_problem(
                "r-furniture", "when.amount_max must be a quoted decimal, got a number"
            ),
            rule_problem(
                "r-mobilepay-netto", 'then.category "food-out" is not in taxonomy.toml'
            ),
        )

    def test_a_rule_may_name_only_a_declared_account(self) -> None:
        rules = RULES.replace('"joint-savings"', '"joint-credit"')

        assert refusal(rules=rules) == (
            rule_problem(
                "r-interest-correction",
                'when.account "joint-credit" is not in accounts.toml',
            ),
        )

    def test_every_when_key_holds_its_declared_type(self) -> None:
        text = "must be a non-empty string"
        patterns = f"{text} or a list of them"
        amount = 'must be a quoted decimal such as "-1000.00"'
        day = "must be a date such as 2026-01-31"
        for line, expected in (
            ("account = 5", f"account {text}"),
            ('description_contains = ""', f"description_contains {patterns}"),
            ("description_starts_with = []", f"description_starts_with {patterns}"),
            ('description_contains = ["NETTO", 5]', f"description_contains {patterns}"),
            (
                'description_regex = ["NETTO", "NETTO("]',
                "description_regex must hold valid regular expressions",
            ),
            ('amount_sign = "minus"', "amount_sign must be one of negative, positive"),
            ('amount_min = "ten"', f"amount_min {amount}"),
            ('amount_min = "NaN"', f"amount_min {amount}"),
            ('date_from = "2026-01-01"', f"date_from {day}"),
            ("date_to = 2026-01-31T00:00:00", f"date_to {day}"),
            ('bank_category = ""', f"bank_category {text}"),
            ("bank_subcategory = 1", f"bank_subcategory {text}"),
        ):
            rules = f'format = 1\n[[rule]]\nid = "r-netto"\nwhen.{line}\n'
            rules += 'then.adjustment = "x"\n'
            with self.subTest(line=line):
                assert refusal(rules=rules) == (
                    rule_problem("r-netto", f"when.{expected}"),
                )

    def test_an_unknown_when_key_is_a_configuration_error(self) -> None:
        rules = RULES.replace("when.bank_category", "when.bank_label")

        assert refusal(rules=rules) == (
            rule_problem("r-bank-groceries", 'unknown key "when.bank_label"'),
        )

    def test_when_is_a_table_of_conditions(self) -> None:
        rules = 'format = 1\n[[rule]]\nid = "r-netto"\nwhen = "NETTO"\n'
        rules += 'then.adjustment = "x"\n'

        assert refusal(rules=rules) == (
            rule_problem("r-netto", "when must be a table of conditions"),
        )


if __name__ == "__main__":
    unittest.main()
