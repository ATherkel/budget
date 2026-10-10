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
    GoldCategoryAllocation,
    GoldTransaction,
    TransactionType,
)
from budget.inputs.rules import AssignCategory, RuleConditions
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


def classify(
    transactions: Sequence[GoldTransaction],
    silver: Iterable[Transaction],
    configuration: ConfigurationSnapshot,
) -> tuple[tuple[GoldTransaction, ...], tuple[GoldCategoryAllocation, ...]]:
    """Type each transaction, and allocate each classified one whole.

    A rule tests the Silver row's own facts, so `silver` must hold every
    transaction's parent row.
    """
    facts = {t.transaction_id: t for t in silver}
    outcomes = [
        (t, _outcome(facts[t.transaction_id], configuration)) for t in transactions
    ]
    return (
        tuple(replace(t, transaction_type=o.transaction_type) for t, o in outcomes),
        tuple(
            _allocation(t, o.category_id)
            for t, o in outcomes
            if o.category_id is not None
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
        return _Outcome("unknown")
    winner = max(matching, key=lambda rule: rule.priority)
    match winner.then:
        case AssignCategory(category_id=category_id):
            taxonomy = configuration.taxonomy
            group_id = taxonomy.categories[category_id].group_id
            direction = taxonomy.groups[group_id].direction
            return _Outcome(_derived_type(direction, transaction.amount), category_id)
        case _:
            return _Outcome("unknown")


def _matches(when: RuleConditions, transaction: Transaction) -> bool:
    """Say whether the transaction's text contains one of the rule's patterns."""
    text = transaction.description.casefold()
    return any(pattern.casefold() in text for pattern in when.description_contains)


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
