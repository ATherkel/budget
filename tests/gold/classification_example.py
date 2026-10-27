# Copyright 2026 Therkel
"""The synthetic setup of `classification.md` as the inputs `gold.build` reads.

The accounts, taxonomy and rules are the doc's *Setup* tables. Each scenario
supplies its own Silver transactions, named by a short invented identifier.
Every account, text and amount is invented.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from typing import Literal

from budget.gold import CategoryDirection, GoldResult, build
from budget.gold.decisions import GoldDecision
from budget.inputs import (
    Account,
    AssignCategory,
    Category,
    CategoryGroup,
    ClaimTransfer,
    ConfigurationSnapshot,
    Rule,
    RuleConditions,
    RuleOutcome,
    Taxonomy,
)
from budget.silver import SilverResult, Transaction
from tests.gold.invariants import assert_contract_invariants
from tests.gold.worked_example import PUBLICATION
from tests.gold.worked_silver import LATE_BOOKING_WINDOW, silver_transaction

CURRENT = "joint-current"
SAVINGS = "joint-savings"
ANNA = "anna-current"


def _account(
    account_id: str,
    account_type: Literal["current", "savings"],
    ownership_scope: Literal["household", "person"],
) -> Account:
    return Account(
        account_id=account_id,
        display_name=account_id,
        account_type=account_type,
        ownership_scope=ownership_scope,
        currency="DKK",
        source_format="danske-csv-v1",
    )


ACCOUNTS: Mapping[str, Account] = {
    CURRENT: _account(CURRENT, "current", "household"),
    SAVINGS: _account(SAVINGS, "savings", "household"),
    ANNA: _account(ANNA, "current", "person"),
}

# Each group's direction and its categories.
_GROUPS: Mapping[str, tuple[CategoryDirection, tuple[str, ...]]] = {
    "income": ("income", ("salary", "interest", "contribution")),
    "housing": ("expense", ("rent", "utilities")),
    "food": ("expense", ("groceries", "eating-out")),
    "home": ("expense", ("household-goods",)),
    "personal": ("expense", ("health", "gifts")),
    "saving": ("expense", ("external-saving",)),
}

TAXONOMY = Taxonomy(
    groups={
        group_id: CategoryGroup(group_id, group_id.title(), direction)
        for group_id, (direction, _) in _GROUPS.items()
    },
    categories={
        category_id: Category(category_id, category_id.title(), group_id)
        for group_id, (_, category_ids) in _GROUPS.items()
        for category_id in category_ids
    },
)


def _rule(
    rule_id: str, when: RuleConditions, then: RuleOutcome, priority: int = 0
) -> Rule:
    return Rule(rule_id, priority, when, then)


def _contains(*text: str) -> RuleConditions:
    return RuleConditions(description_contains=text)


RULES: Mapping[str, Rule] = {
    rule.rule_id: rule
    for rule in (
        _rule("r-salary", _contains("ACME PAYROLL"), AssignCategory("salary")),
        _rule(
            "r-interest",
            RuleConditions(account=SAVINGS, description_contains=("INTEREST",)),
            AssignCategory("interest"),
        ),
        _rule(
            "r-contribution-bo", _contains("FROM BO"), AssignCategory("contribution")
        ),
        _rule("r-netto", _contains("NETTO"), AssignCategory("groceries")),
        _rule(
            "r-mobilepay",
            RuleConditions(description_starts_with=("MOBILEPAY",)),
            AssignCategory("eating-out"),
        ),
        _rule("r-home", _contains("IKEA"), AssignCategory("household-goods")),
        _rule("r-dentist", _contains("DENTIST"), AssignCategory("health")),
        _rule(
            "r-savings-transfer",
            _contains("TO SAVINGS", "FROM CURRENT"),
            ClaimTransfer(),
        ),
        _rule("r-budget-transfer", _contains("BUDGET"), ClaimTransfer()),
        _rule(
            "r-bank-groceries",
            RuleConditions(bank_category="Groceries"),
            AssignCategory("groceries"),
            priority=-10,
        ),
    )
}


def booked(
    transaction_id: str,
    account_id: str,
    transaction_date: date,
    amount: str,
    description: str,
) -> Transaction:
    """One booked Silver transaction in DKK, stating no balance or bank label."""
    return replace(
        silver_transaction(transaction_id, account_id, transaction_date, amount, None),
        description=description,
    )


def classified(
    *transactions: Transaction,
    rules: Mapping[str, Rule] = RULES,
    taxonomy: Taxonomy = TAXONOMY,
    accounts: Mapping[str, Account] = ACCOUNTS,
    decisions: Sequence[GoldDecision] = (),
) -> GoldResult:
    """Run the Gold build over these transactions, decisions and configuration.

    Every result must keep contract invariants 10 and 12, so each scenario
    checks them too.
    """
    result = build(
        silver=SilverResult(
            transactions=transactions,
            transaction_evidence=(),
            unbooked_records=(),
            balance_observations=(),
            account_evidence=(),
            evidence_exports=(),
            import_run_results=(),
            review_items=(),
        ),
        configuration=ConfigurationSnapshot(
            accounts=accounts, taxonomy=taxonomy, rules=rules
        ),
        decisions=decisions,
        publication=PUBLICATION,
        late_booking_window=LATE_BOOKING_WINDOW,
    )
    assert_contract_invariants(result)
    return result
