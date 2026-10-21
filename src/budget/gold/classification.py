# Copyright 2026 Therkel
"""Classification by rules: each transaction's type and its one allocation.

The highest-priority matching rule decides (`classification.md`, *Precedence*;
ADR-011). A category's type follows from its direction and the amount's sign,
and a classified transaction has one allocation for its whole amount (ADR-008).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from budget.gold.models import (
    CategoryDirection,
    ClassificationReviewItem,
    ClassificationReviewKind,
    GoldCategoryAllocation,
    GoldTransaction,
    TransactionType,
)
from budget.hashing import hash_parts
from budget.inputs.rules import AssignCategory, RuleConditions, fold
from budget.inputs.snapshot import ConfigurationSnapshot
from budget.silver.models import Transaction

type _Sign = Literal["negative", "positive"]

# The type a category gives (classification.md, *What a rule may assign*).
_CATEGORY_TYPES: Mapping[tuple[CategoryDirection, _Sign], TransactionType] = (
    MappingProxyType(
        {
            ("expense", "negative"): "expense",
            ("expense", "positive"): "refund",
            ("income", "positive"): "income",
            ("income", "negative"): "refund",
        }
    )
)


@dataclass(frozen=True)
class _Outcome:
    """What classification decided for one transaction."""

    transaction_type: TransactionType
    category_id: str | None = None
    # The kind of review item the outcome raises, if any.
    review_kind: ClassificationReviewKind | None = None
    rule_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Classified:
    """Classification's output: typed transactions and what they give rise to."""

    transactions: tuple[GoldTransaction, ...]
    allocations: tuple[GoldCategoryAllocation, ...]
    review_items: tuple[ClassificationReviewItem, ...]


def classify(
    transactions: Sequence[GoldTransaction],
    silver: Iterable[Transaction],
    configuration: ConfigurationSnapshot,
) -> Classified:
    """Type each transaction, allocate each classified one whole, and raise items.

    A rule tests the Silver row's own facts, so `silver` must hold every
    transaction's parent row.
    """
    facts = {t.transaction_id: t for t in silver}
    outcomes = [
        (t, _outcome(facts[t.transaction_id], configuration)) for t in transactions
    ]
    return Classified(
        transactions=tuple(
            replace(t, transaction_type=o.transaction_type) for t, o in outcomes
        ),
        allocations=tuple(
            _allocation(t, o.category_id)
            for t, o in outcomes
            if o.category_id is not None
        ),
        review_items=tuple(
            item for t, o in outcomes if (item := _review_item(t, o)) is not None
        ),
    )


def _outcome(
    transaction: Transaction, configuration: ConfigurationSnapshot
) -> _Outcome:
    """Classify one transaction by the highest-priority rule it matches."""
    matching = [
        rule
        for rule in configuration.rules.values()
        if _matches(rule.when, transaction)
    ]
    if not matching:
        return _Outcome("unknown", review_kind="unclassified")

    winner = max(matching, key=lambda rule: rule.priority)
    ties = [rule for rule in matching if rule.priority == winner.priority]
    if any(rule.then != winner.then for rule in ties):
        return _Outcome(
            "unknown",
            review_kind="rule-conflict",
            rule_ids=tuple(sorted(rule.rule_id for rule in ties)),
        )

    match winner.then:
        case AssignCategory(category_id=category_id):
            taxonomy = configuration.taxonomy
            group_id = taxonomy.categories[category_id].group_id
            direction = taxonomy.groups[group_id].direction
            return _Outcome(_derived_type(direction, transaction.amount), category_id)
        case _:
            return _Outcome("unknown")


def _matches(when: RuleConditions, transaction: Transaction) -> bool:
    """Say whether the transaction meets every condition the rule sets.

    A condition the rule leaves unset holds, but a rule that sets none
    matches nothing, so it cannot silently classify every transaction.
    """
    description_holds = when.matches_description(transaction.description)
    bank_category_holds = when.bank_category is None or (
        transaction.bank_category is not None
        and fold(when.bank_category) == fold(transaction.bank_category)
    )
    sets_a_condition = bool(
        when.description_contains
        or when.description_starts_with
        or when.description_regex
        or when.bank_category is not None
    )
    return description_holds and bank_category_holds and sets_a_condition


def _derived_type(direction: CategoryDirection, amount: Decimal) -> TransactionType:
    """Derive a category's type from its direction and the amount's sign."""
    if amount == Decimal(0):
        return "unknown"
    sign: _Sign = "positive" if amount > 0 else "negative"
    return _CATEGORY_TYPES[(direction, sign)]


def _allocation(
    transaction: GoldTransaction, category_id: str
) -> GoldCategoryAllocation:
    """Allocate the whole transaction to one category (ADR-008)."""
    return GoldCategoryAllocation(
        allocation_id=f"{transaction.transaction_id}/{category_id}",
        transaction_id=transaction.transaction_id,
        account_id=transaction.account_id,
        transaction_date=transaction.transaction_date,
        category_id=category_id,
        amount=transaction.amount,
    )


def _review_item(
    transaction: GoldTransaction, outcome: _Outcome
) -> ClassificationReviewItem | None:
    """Raise the review item an outcome calls for; most call for none."""
    if outcome.review_kind is None:
        return None

    return ClassificationReviewItem(
        review_item_id=hash_parts([outcome.review_kind, transaction.transaction_id]),
        kind=outcome.review_kind,
        transaction_ids=(transaction.transaction_id,),
        rule_ids=outcome.rule_ids or (),
        decision_id=None,
        reason=None,
    )
