# Copyright 2026 Therkel
"""Classification: each transaction's type and its one allocation.

An applicable manual decision decides first, then a transfer pair, then the
highest-priority matching rule (`classification.md`, *Precedence*; ADR-011).
A category's type follows from its direction and the amount's sign,
and a classified transaction has one allocation for its whole amount (ADR-008).
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Literal

from budget.gold.decisions import (
    Classify,
    ClassifyAdjustment,
    GoldDecision,
    OneSidedTransfer,
    Pair,
    log_kind,
    targets,
)
from budget.gold.models import (
    CategoryDirection,
    ClassificationReviewItem,
    ClassificationReviewKind,
    ClassificationSource,
    GoldCategoryAllocation,
    GoldTransaction,
    GoldTransactionLineage,
    ReportingMonth,
    TransactionType,
    TransferEvidence,
)
from budget.gold.transfers import Matching, date_gap, match_transfers, pair_legs
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
    # Every transaction the review item names, when it is not this one alone.
    review_transaction_ids: tuple[str, ...] = ()
    # The rules the review item names, when they are not `rule_ids`.
    review_rule_ids: tuple[str, ...] | None = None
    # Whether the winning rule claims the transaction as a transfer leg.
    claims_transfer: bool = False
    transfer_group_id: str | None = None
    transfer_evidence: TransferEvidence | None = None
    # The manual decision that decided, if one did.
    decision_id: str | None = None


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
    decisions: Sequence[GoldDecision],
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
    claims = {tid: o.rule_ids for tid, o in by_rule.items() if o.claims_transfer}
    decided = _decided(
        decisions,
        _Inputs(
            {t.transaction_id: t for t in transactions},
            by_rule,
            claims,
            configuration,
        ),
    )
    matching = match_transfers(
        transactions,
        claims=claims,
        closed_on={a.account_id: a.closed_on for a in configuration.accounts.values()},
        decided=decided.outcomes.keys(),
    )
    outcomes = [
        (
            t,
            _settled(by_rule[t.transaction_id], t.transaction_id, matching)
            if (manual := decided.outcomes.get(t.transaction_id)) is None
            else manual,
        )
        for t in transactions
    ]
    items = {t.transaction_id: _review_item(t, o) for t, o in outcomes}
    version = _classification_version(configuration, decisions)
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
        review_items=(
            *{i.review_item_id: i for i in items.values() if i is not None}.values(),
            *decided.not_applicable,
        ),
        lineage=tuple(
            _lineage(
                facts[t.transaction_id],
                o,
                version,
                (items[t.transaction_id], *decided.not_applicable),
            )
            for t, o in outcomes
        ),
    )


def _classification_version(
    configuration: ConfigurationSnapshot, decisions: Sequence[GoldDecision]
) -> str:
    """Fingerprint the classification inputs (`publications.md`).

    They are the configuration snapshot and the effective decisions, each
    decision written as its decision-log kind and fields, in any order.
    """
    return hash_parts(
        [
            configuration.fingerprint,
            *sorted(
                json.dumps([log_kind(d), asdict(d)], sort_keys=True) for d in decisions
            ),
        ]
    )


@dataclass(frozen=True)
class _Inputs:
    """What a decision is applied against, by transaction_id."""

    transactions: Mapping[str, GoldTransaction]
    by_rule: Mapping[str, _Outcome]
    # The rules claiming each claimed leg as a transfer.
    claims: Mapping[str, tuple[str, ...]]
    configuration: ConfigurationSnapshot


@dataclass(frozen=True)
class _Decided:
    """The outcomes applicable decisions give, and the items the rest raise."""

    outcomes: Mapping[str, _Outcome]
    not_applicable: tuple[ClassificationReviewItem, ...]


def _decided(decisions: Sequence[GoldDecision], inputs: _Inputs) -> _Decided:
    """Settle each transaction an applicable decision targets (*Precedence*).

    The rules that matched stay in the outcome for lineage, though they did
    not decide. A decision that is not applicable changes nothing and raises
    a `decision-not-applicable` item naming it (*Manual Decisions*).
    """
    outcomes: dict[str, _Outcome] = {}
    not_applicable: list[ClassificationReviewItem] = []
    for decision in decisions:
        reason = _inapplicable(decision, inputs)
        if reason is None:
            outcomes.update(_applied(decision, inputs))
        else:
            not_applicable.append(_not_applicable_item(decision, reason, inputs))
    return _Decided(outcomes, tuple(not_applicable))


def _inapplicable(decision: GoldDecision, inputs: _Inputs) -> str | None:
    """Say why a decision does not apply, or `None` when it does."""
    if any(tid not in inputs.transactions for tid in targets(decision)):
        return "target-missing"
    match decision:
        case Classify(transaction_id=tid):
            if _sign(inputs.transactions[tid].amount) is None:
                return "zero-amount"
        case Pair(transaction_ids=(first, second)):
            out, into = inputs.transactions[first], inputs.transactions[second]
            if out.amount + into.amount != 0:
                return "amounts-do-not-cancel"
            if out.account_id == into.account_id:
                return "same-account"
        case OneSidedTransfer(transaction_id=tid, counterpart_account_id=account_id):
            if _managed_in(
                account_id, inputs.transactions[tid].transaction_date, inputs
            ):
                return "inside-managed-period"
        case _:
            pass
    return None


def _managed_in(account_id: str, day: date, inputs: _Inputs) -> bool:
    """Say whether the day's month is in the account's managed period.

    The period runs from the month of the account's first booked transaction
    to the month of `closed_on`, if any (`gold-contract.md`,
    *MonthlyBalanceSnapshot*); an account with none has no period yet. Its cap
    at the latest published month never binds: no transaction falls after it.
    """
    booked = [
        t.transaction_date
        for t in inputs.transactions.values()
        if t.account_id == account_id
    ]
    if not booked:
        return False
    month = ReportingMonth.of(day)
    closed_on = inputs.configuration.accounts[account_id].closed_on
    return ReportingMonth.of(min(booked)) <= month and (
        closed_on is None or month <= ReportingMonth.of(closed_on)
    )


def _not_applicable_item(
    decision: GoldDecision, reason: str, inputs: _Inputs
) -> ClassificationReviewItem:
    """Raise the item naming a decision that is not applicable.

    It names the targets still present; none when a single target is missing.
    """
    present = tuple(tid for tid in targets(decision) if tid in inputs.transactions)
    kind: ClassificationReviewKind = "decision-not-applicable"
    return ClassificationReviewItem(
        review_item_id=hash_parts([kind, decision.decision_id, *present]),
        kind=kind,
        transaction_ids=present,
        rule_ids=(),
        decision_id=decision.decision_id,
        reason=reason,
    )


def _applied(decision: GoldDecision, inputs: _Inputs) -> dict[str, _Outcome]:
    """Give each transaction one decision targets its outcome."""
    match decision:
        case Classify(transaction_id=tid, category_id=category_id):
            transaction_type = _category_type(
                category_id, inputs.transactions[tid].amount, inputs.configuration
            )
            return {
                tid: _Outcome(
                    transaction_type,
                    category_id,
                    rule_ids=inputs.by_rule[tid].rule_ids,
                    decision_id=decision.decision_id,
                )
            }
        case ClassifyAdjustment(transaction_id=tid, reason=reason):
            return {
                tid: _Outcome(
                    "adjustment",
                    rule_ids=inputs.by_rule[tid].rule_ids,
                    adjustment_reason=reason,
                    decision_id=decision.decision_id,
                )
            }
        case Pair(transaction_ids=(first, second)):
            out, into = inputs.transactions[first], inputs.transactions[second]
            legs = pair_legs(
                out, into, inputs.claims, date_gap(out, into), "manual_pair"
            )
            return {
                tid: _Outcome(
                    "transfer",
                    rule_ids=inputs.by_rule[tid].rule_ids,
                    transfer_group_id=leg.transfer_group_id,
                    transfer_evidence=leg.evidence,
                    decision_id=decision.decision_id,
                )
                for tid, leg in legs.items()
            }
        case OneSidedTransfer(
            transaction_id=tid, counterpart_account_id=counterpart_account_id
        ):
            evidence = TransferEvidence(
                basis="one_sided",
                counterpart_account_id=counterpart_account_id,
                counterpart_transaction_id=None,
                date_gap_days=None,
                claim_rule_ids=inputs.claims.get(tid, ()),
            )
            return {
                tid: _Outcome(
                    "transfer",
                    rule_ids=inputs.by_rule[tid].rule_ids,
                    transfer_evidence=evidence,
                    decision_id=decision.decision_id,
                )
            }


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
    held = matching.ambiguous.get(transaction_id)
    if held is not None:
        return _Outcome(
            "unknown",
            review_kind="ambiguous-transfer",
            rule_ids=rule_result.rule_ids,
            review_rule_ids=held.claim_rule_ids,
            review_transaction_ids=held.transaction_ids,
        )
    reason = matching.unmatched.get(transaction_id)
    if reason is None:
        return rule_result
    return replace(rule_result, review_reason=reason)


def _lineage(
    silver: Transaction,
    outcome: _Outcome,
    classification_version: str,
    review_items: Iterable[ClassificationReviewItem | None],
) -> GoldTransactionLineage:
    """Record which rules, decision and review items stand behind one type.

    The rules decided only when they gave the transaction a type, and no
    applicable decision did. Of `review_items`, lineage keeps those that name
    this transaction.
    """
    decided = bool(outcome.rule_ids) and outcome.transaction_type != "unknown"
    source: ClassificationSource = "rule" if decided else "unclassified"
    if outcome.transfer_evidence is not None:
        source = "transfer_match"
    if outcome.decision_id is not None:
        source = "manual"
    return GoldTransactionLineage(
        transaction_id=silver.transaction_id,
        silver_transaction_id=silver.transaction_id,
        classification_source=source,
        rule_ids=outcome.rule_ids,
        decision_id=outcome.decision_id,
        classification_version=classification_version,
        transfer_evidence=outcome.transfer_evidence,
        review_item_ids=tuple(
            item.review_item_id
            for item in review_items
            if item is not None and silver.transaction_id in item.transaction_ids
        ),
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
            transaction_type = _category_type(
                category_id, transaction.amount, configuration
            )
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


def _category_type(
    category_id: str, amount: Decimal, configuration: ConfigurationSnapshot
) -> TransactionType:
    """Derive the type a category gives this amount, through its group."""
    taxonomy = configuration.taxonomy
    group_id = taxonomy.categories[category_id].group_id
    return _derived_type(taxonomy.groups[group_id].direction, amount)


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

    transaction_ids = outcome.review_transaction_ids or (transaction.transaction_id,)
    return ClassificationReviewItem(
        review_item_id=hash_parts([outcome.review_kind, *transaction_ids]),
        kind=outcome.review_kind,
        transaction_ids=transaction_ids,
        rule_ids=(
            outcome.rule_ids
            if outcome.review_rule_ids is None
            else outcome.review_rule_ids
        ),
        decision_id=None,
        reason=outcome.review_reason,
    )
