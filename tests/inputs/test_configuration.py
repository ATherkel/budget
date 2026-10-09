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


class EveryFileTests(unittest.TestCase):
    def test_every_file_is_judged_before_stopping(self) -> None:
        # A refused file declares nothing a rule can be checked against, so no
        # reference into it is judged.
        accounts = ACCOUNTS.replace("format = 1\n", 'format = 1\ncolour = "blue"\n')
        taxonomy = TAXONOMY.replace('"expense"', '"spending"', 1)
        rules = RULES.replace('"-1000.00"', "-1000.00").replace(
            'then.category = "groceries"', 'then.category = "food-out"'
        )

        assert refusal(accounts, taxonomy, rules) == (
            'accounts.toml: unknown key "colour"',
            'taxonomy.toml: group "food": direction must be one of income, expense',
            rule_problem(
                "r-furniture", "when.amount_max must be a quoted decimal, got a number"
            ),
        )

    def test_a_missing_file_is_named_beside_the_others_problems(self) -> None:
        with TemporaryDirectory() as directory:
            profile = make_test_profile(directory)
            profile.inputs.mkdir(parents=True)
            profile.input_file("accounts.toml").write_text(ACCOUNTS, encoding="utf-8")
            rules = RULES.replace('"-1000.00"', "-1000.00")
            profile.input_file("rules.toml").write_text(rules, encoding="utf-8")

            with pytest.raises(ConfigurationError) as refused:
                load_configuration(profile)

        assert refused.value.problems == (
            "taxonomy.toml: the file is missing",
            rule_problem(
                "r-furniture", "when.amount_max must be a quoted decimal, got a number"
            ),
        )


class TaxonomyProblemTests(unittest.TestCase):
    def test_every_broken_entry_is_named_with_its_problems(self) -> None:
        # Groups are judged before categories, each in file order.
        taxonomy = """\
format = 1
shade = 1

[group.food]
name = "Food"
direction = "spending"

[category.groceries]
name = "Groceries"
group = "food"
direction = "expense"

[group.Home]
name = ""

[category.rent]
name = "Rent"
group = "housing"

[category.eating-out]
name = "Eating out"
"""
        rules = 'format = 1\n[[rule]]\nid = "r-netto"\nthen.transfer_claim = true\n'

        assert refusal(taxonomy=taxonomy, rules=rules) == (
            'taxonomy.toml: unknown key "shade"',
            'taxonomy.toml: group "food": direction must be one of income, expense',
            (
                'taxonomy.toml: group "Home": the ID must be lowercase words '
                "joined by hyphens, such as food"
            ),
            'taxonomy.toml: group "Home": name must be a non-empty string',
            'taxonomy.toml: group "Home": direction is missing',
            'taxonomy.toml: category "groceries": unknown key "direction"',
            'taxonomy.toml: category "rent": group "housing" is not declared',
            'taxonomy.toml: category "eating-out": group is missing',
        )

    def test_each_kind_holds_one_table_per_entry(self) -> None:
        for content, expected in (
            ("group = 1", "group must hold one [group.<id>] table per group"),
            (
                "category = 1",
                "category must hold one [category.<id>] table per category",
            ),
            ('group.food = "Food"', 'group "food": must be a table of keys'),
        ):
            with self.subTest(content=content):
                taxonomy = f"format = 1\n{content}\n"
                assert refusal(taxonomy=taxonomy, rules="format = 1\n") == (
                    f"taxonomy.toml: {expected}",
                )


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

    def test_every_broken_rule_is_named_with_its_problems_in_file_order(
        self,
    ) -> None:
        rules = """\
format = 1
colour = "blue"

[[rule]]
id = "r-netto"
weight = 3
then.category = "groceries"

[[rule]]
id = "r-netto"
priority = 1.5
then.category = "groceries"

[[rule]]
id = "R Netto"
priority = true
then.category = "groceries"

[[rule]]
id = 5
then.category = "groceries"

[[rule]]
then.category = "groceries"
"""
        assert refusal(rules=rules) == (
            'rules.toml: unknown key "colour"',
            rule_problem("r-netto", 'unknown key "weight"'),
            rule_problem("r-netto", "the ID is already used by an earlier rule"),
            rule_problem("r-netto", "priority must be an integer"),
            rule_problem(
                "R Netto",
                "the ID must be lowercase words joined by hyphens, such as r-netto",
            ),
            rule_problem("R Netto", "priority must be an integer"),
            "rules.toml: rule 4: id must be a non-empty string",
            "rules.toml: rule 5: id is missing",
        )

    def test_rule_holds_one_block_per_rule(self) -> None:
        for content, expected in (
            ("rule = 1", "rules.toml: rule must hold one [[rule]] block per rule"),
            (
                '[rule.r-netto]\nthen.category = "groceries"',
                "rules.toml: rule must hold one [[rule]] block per rule",
            ),
            ("rule = [1]", "rules.toml: rule 1: must be a table of keys"),
        ):
            with self.subTest(content=content):
                rules = f"format = 1\n{content}\n"
                assert refusal(rules=rules) == (expected,)

    def test_then_holds_exactly_one_outcome(self) -> None:
        one = "then must hold exactly one of category, transfer_claim, adjustment"
        for lines, expected in (
            ("", (one,)),
            ("then = {}", (one,)),
            ('then = "groceries"', (one,)),
            ('then.category = "groceries"\nthen.transfer_claim = true', (one,)),
            ('then.counterpart = "x"', ('unknown key "then.counterpart"', one)),
            ("then.transfer_claim = false", ("then.transfer_claim must be true",)),
            ('then.adjustment = ""', ("then.adjustment must be a non-empty string",)),
            ("then.category = 5", ("then.category must be a non-empty string",)),
        ):
            rules = f'format = 1\n[[rule]]\nid = "r-netto"\n{lines}\n'
            with self.subTest(lines=lines):
                assert refusal(rules=rules) == tuple(
                    rule_problem("r-netto", problem) for problem in expected
                )

    def test_when_is_a_table_of_conditions(self) -> None:
        rules = 'format = 1\n[[rule]]\nid = "r-netto"\nwhen = "NETTO"\n'
        rules += 'then.adjustment = "x"\n'

        assert refusal(rules=rules) == (
            rule_problem("r-netto", "when must be a table of conditions"),
        )


if __name__ == "__main__":
    unittest.main()
