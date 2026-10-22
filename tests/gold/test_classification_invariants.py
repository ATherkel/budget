# Copyright 2026 Therkel
"""Rule classification keeps `gold-contract.md`'s invariants 3-7 and 19.

The result classifies every rule-only scenario of `classification.md` at once,
plus an adjustment and a zero amount, so each invariant is checked against
every type rules can give. Transfer claims are left out: until transfer
matching exists they stay `unknown` without the `unmatched-transfer` item
invariant 19 asks for.
"""

from collections import Counter
from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.gold import CategoryDirection, GoldResult, GoldTransaction
from budget.inputs import AssignAdjustment, Rule, RuleConditions
from tests.gold.classification_example import (
    ANNA,
    CURRENT,
    RULES,
    SAVINGS,
    TAXONOMY,
    booked,
    classified,
)

_CORRECTION = Rule(
    "r-interest-correction",
    0,
    RuleConditions(account=SAVINGS, description_starts_with=("RENTEKORR",)),
    AssignAdjustment("Bank's interest correction"),
)


def _every_rule_outcome() -> GoldResult:
    labelled = booked("foetex", CURRENT, date(2026, 2, 14), "-310.00", "FOETEX 88")
    return classified(
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        booked("return", CURRENT, date(2026, 2, 12), "120.00", "NETTO 0412"),
        replace(labelled, bank_category="Groceries"),
        booked("conflict", CURRENT, date(2026, 2, 20), "-85.00", "MOBILEPAY NETTO"),
        booked("interest-adj", SAVINGS, date(2026, 3, 31), "-3.50", "INTEREST ADJ"),
        booked("interest", SAVINGS, date(2026, 3, 31), "12.00", "INTEREST"),
        booked("zero", SAVINGS, date(2026, 4, 30), "0.00", "INTEREST ADJ"),
        booked("from-bo", CURRENT, date(2026, 2, 1), "4000.00", "FROM BO"),
        booked("cafe", ANNA, date(2026, 3, 12), "250.00", "MOBILEPAY CARL"),
        booked("cash", CURRENT, date(2026, 2, 3), "-200.00", "ATM 17"),
        booked("fix", SAVINGS, date(2026, 3, 31), "-7.25", "RENTEKORR 2026"),
        rules={**RULES, _CORRECTION.rule_id: _CORRECTION},
    )


def _transactions(result: GoldResult) -> list[GoldTransaction]:
    return list(result.transactions(start_date=date.min, end_date=date.max))


def _direction(category_id: str) -> CategoryDirection:
    group_id = TAXONOMY.categories[category_id].group_id
    return TAXONOMY.groups[group_id].direction


def test_every_type_rules_give_is_exercised() -> None:
    types = {t.transaction_type for t in _transactions(_every_rule_outcome())}

    assert types == {"income", "expense", "refund", "adjustment", "unknown"}


def test_3_and_7_signs_and_category_directions_follow_the_type() -> None:
    result = _every_rule_outcome()
    by_id = {t.transaction_id: t for t in _transactions(result)}

    for allocation in result.category_allocations(
        start_date=date.min, end_date=date.max
    ):
        transaction = by_id[allocation.transaction_id]
        direction = _direction(allocation.category_id)
        positive = transaction.amount > 0
        with_type = (transaction.transaction_type, direction, positive)
        assert with_type in {
            ("expense", "expense", False),
            ("income", "income", True),
            ("refund", "expense", True),
            ("refund", "income", False),
        }, allocation


def test_4_to_6_a_classified_transaction_has_one_whole_allocation() -> None:
    result = _every_rule_outcome()
    allocations = list(
        result.category_allocations(start_date=date.min, end_date=date.max)
    )
    by_transaction = Counter(a.transaction_id for a in allocations)

    for transaction in _transactions(result):
        classified_type = transaction.transaction_type in {
            "income",
            "expense",
            "refund",
        }
        assert by_transaction[transaction.transaction_id] == (
            1 if classified_type else 0
        ), transaction
    for allocation in allocations:
        transaction = next(
            t
            for t in _transactions(result)
            if t.transaction_id == allocation.transaction_id
        )
        assert allocation.amount == transaction.amount != Decimal(0)
        assert allocation.account_id == transaction.account_id
        assert allocation.transaction_date == transaction.transaction_date
    assert len({a.allocation_id for a in allocations}) == len(allocations)


def test_19_every_type_traces_to_its_rules_and_every_unknown_to_an_item() -> None:
    result = _every_rule_outcome()
    transactions = _transactions(result)
    lineage = {
        line.transaction_id: line
        for line in result.transaction_lineage([t.transaction_id for t in transactions])
    }
    involved = {
        transaction_id
        for item in result.classification_review_items()
        for transaction_id in item.transaction_ids
    }

    for transaction in transactions:
        line = lineage[transaction.transaction_id]
        if transaction.transaction_type == "unknown":
            assert line.classification_source == "unclassified", line
            assert transaction.transaction_id in involved, transaction
        else:
            assert line.classification_source == "rule", line
            assert line.rule_ids, line
