# Copyright 2026 Therkel
"""Classification by rules: each transaction's type and its one allocation.

The highest-priority matching rule decides (`classification.md`, *Precedence*;
ADR-011). A category's type follows from its direction and the amount's sign,
and a classified transaction has one allocation for its whole amount (ADR-008).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from budget.gold.models import (
    CategoryDirection,
    ClassificationReviewItem,
    ClassificationReviewKind,
    ClassificationSource,
    GoldCategoryAllocation,
    GoldTransaction,
    GoldTransactionLineage,
    TransactionType,
    TransferEvidence,
)
from budget.gold.transfers import Matching, match_transfers
from budget.hashing import hash_parts
from budget.inputs.rules import (
    AssignAdjustment,
    AssignCategory,
    RuleConditions,
    fold,
)
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
    # The explanation an adjustment carries into lineage.
    adjustment_reason: str | None = None
    # Why the review item was raised, where its kind names reasons.
    review_reason: str | None = None
    # Whether the winning rule claims the transaction as a transfer leg.
    claims_transfer: bool = False
    transfer_group_id: str | None = None
    transfer_evidence: TransferEvidence | None = None


@dataclass(frozen=True)
class Classified:
    """Classification's output: typed transactions and what they give rise to."""

    transactions: tuple[GoldTransaction, ...]
    allocations: tuple[GoldCategoryAllocation, ...]
    review_items: tuple[ClassificationReviewItem, ...]
    lineage: tuple[GoldTransactionLineage, ...]


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
    by_rule = {
        t.transaction_id: _outcome(facts[t.transaction_id], configuration)
        for t in transactions
    }
    matching = match_transfers(
        transactions,
        claims={tid: o.rule_ids for tid, o in by_rule.items() if o.claims_transfer},
        account_ids=configuration.accounts.keys(),
    )
    outcomes = [
        (t, _settled(by_rule[t.transaction_id], t.transaction_id, matching))
        for t in transactions
    ]
    items = {t.transaction_id: _review_item(t, o) for t, o in outcomes}
    version = configuration.fingerprint
    return Classified(
        transactions=tuple(
            replace(
                t,
                transaction_type=o.transaction_type,
                transfer_group_id=o.transfer_group_id,
            )
            for t, o in outcomes
        ),
        allocations=tuple(
            _allocation(t, o.category_id)
            for t, o in outcomes
            if o.category_id is not None
        ),
        review_items=tuple(item for item in items.values() if item is not None),
        lineage=tuple(
            _lineage(facts[t.transaction_id], o, version, items[t.transaction_id])
            for t, o in outcomes
        ),
    )


def _settled(
    rule_result: _Outcome, transaction_id: str, matching: Matching
) -> _Outcome:
    """Settle a rule result against transfer matching (*Precedence*)."""
    leg = matching.paired.get(transaction_id)
    if leg is not None:
        return _Outcome(
            "transfer",
            rule_ids=rule_result.rule_ids,
            transfer_group_id=leg.transfer_group_id,
            transfer_evidence=leg.evidence,
        )
    reason = matching.unmatched.get(transaction_id)
    if reason is None:
        return rule_result
    return replace(rule_result, review_reason=reason)


def _lineage(
    silver: Transaction,
    outcome: _Outcome,
    classification_version: str,
    review_item: ClassificationReviewItem | None,
) -> GoldTransactionLineage:
    """Record which rules and review item stand behind one transaction's type.

    The rules decided only when they gave the transaction a type; until
    decisions exist, the configuration's fingerprint is the classification
    version.
    """
    decided = bool(outcome.rule_ids) and outcome.transaction_type != "unknown"
    source: ClassificationSource = "rule" if decided else "unclassified"
    if outcome.transfer_evidence is not None:
        source = "transfer_match"
    return GoldTransactionLineage(
        transaction_id=silver.transaction_id,
        silver_transaction_id=silver.transaction_id,
        classification_source=source,
        rule_ids=outcome.rule_ids,
        decision_id=None,
        classification_version=classification_version,
        transfer_evidence=outcome.transfer_evidence,
        review_item_ids=() if review_item is None else (review_item.review_item_id,),
        adjustment_reason=outcome.adjustment_reason,
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
    rule_ids = tuple(sorted(rule.rule_id for rule in ties))
    if any(rule.then != winner.then for rule in ties):
        return _Outcome("unknown", review_kind="rule-conflict", rule_ids=rule_ids)

    match winner.then:
        case AssignCategory(category_id=category_id):
            taxonomy = configuration.taxonomy
            group_id = taxonomy.categories[category_id].group_id
            direction = taxonomy.groups[group_id].direction
            transaction_type = _derived_type(direction, transaction.amount)
            if transaction_type == "unknown":
                return _Outcome(
                    "unknown", review_kind="sign-mismatch", rule_ids=rule_ids
                )
            return _Outcome(transaction_type, category_id, rule_ids=rule_ids)
        case AssignAdjustment(reason=reason):
            return _Outcome("adjustment", rule_ids=rule_ids, adjustment_reason=reason)
        case _:
            return _Outcome(
                "unknown",
                review_kind="unmatched-transfer",
                rule_ids=rule_ids,
                claims_transfer=True,
            )


def _matches(when: RuleConditions, transaction: Transaction) -> bool:
    """Say whether the transaction meets every condition the rule sets.

    A condition the rule leaves unset holds, but a rule that sets none
    matches nothing, so it cannot silently classify every transaction.
    """
    return when.sets_a_condition and all(
        (
            when.account is None or when.account == transaction.account_id,
            when.matches_description(transaction.description),
            when.amount_sign is None or when.amount_sign == _sign(transaction.amount),
            _within(transaction.amount, when.amount_min, when.amount_max),
            _within(transaction.transaction_date, when.date_from, when.date_to),
            _label_holds(when.bank_category, transaction.bank_category),
            _label_holds(when.bank_subcategory, transaction.bank_subcategory),
        )
    )


def _label_holds(wanted: str | None, label: str | None) -> bool:
    """Say whether a bank label meets the rule's, in any case; unset holds."""
    return wanted is None or (label is not None and fold(wanted) == fold(label))


def _within[T: (Decimal, date)](value: T, low: T | None, high: T | None) -> bool:
    """Say whether the value lies in the inclusive range; an unset bound holds."""
    return (low is None or value >= low) and (high is None or value <= high)


def _sign(amount: Decimal) -> _Sign | None:
    """Name the amount's sign; zero has none."""
    if amount == Decimal(0):
        return None
    return "positive" if amount > 0 else "negative"


def _derived_type(direction: CategoryDirection, amount: Decimal) -> TransactionType:
    """Derive a category's type from its direction and the amount's sign."""
    sign = _sign(amount)
    if sign is None:
        return "unknown"
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
        reason=outcome.review_reason,
    )
