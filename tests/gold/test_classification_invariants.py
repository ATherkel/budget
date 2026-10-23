# Copyright 2026 Therkel
"""Classification keeps `gold-contract.md`'s invariants 3-7, 16 and 19.

The result classifies every rule-only scenario of `classification.md` at once,
plus an adjustment, a zero amount, and transfer claims that pair, find no
partner and compete, so each invariant is checked against every type rules and
transfer matching can give.
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
        booked("out", CURRENT, date(2026, 1, 30), "-5000.00", "TO SAVINGS"),
        booked("in", SAVINGS, date(2026, 2, 2), "5000.00", "FROM CURRENT"),
        booked("budget-out", ANNA, date(2026, 3, 2), "-2000.00", "BUDGET JOINT"),
        booked("budget-in", CURRENT, date(2026, 3, 2), "2000.00", "BUDGET"),
        booked("unpaired", CURRENT, date(2026, 2, 16), "-1000.00", "TO SAVINGS"),
        booked("claim", CURRENT, date(2026, 3, 5), "-1500.00", "TO SAVINGS"),
        booked("dentist", CURRENT, date(2026, 3, 5), "-1500.00", "DENTIST 7"),
        booked("held", SAVINGS, date(2026, 3, 5), "1500.00", "FROM CURRENT"),
        rules={**RULES, _CORRECTION.rule_id: _CORRECTION},
    )


def _transactions(result: GoldResult) -> list[GoldTransaction]:
    return list(result.transactions(start_date=date.min, end_date=date.max))


def _direction(category_id: str) -> CategoryDirection:
    group_id = TAXONOMY.categories[category_id].group_id
    return TAXONOMY.groups[group_id].direction


def test_every_type_rules_give_is_exercised() -> None:
    types = {t.transaction_type for t in _transactions(_every_rule_outcome())}

    assert types == {
        "income",
        "expense",
        "refund",
        "transfer",
        "adjustment",
        "unknown",
    }


def test_every_review_kind_rules_and_matching_raise_is_exercised() -> None:
    kinds = {i.kind for i in _every_rule_outcome().classification_review_items()}

    assert kinds == {
        "unclassified",
        "rule-conflict",
        "sign-mismatch",
        "ambiguous-transfer",
        "unmatched-transfer",
    }


def test_16_a_transfer_group_joins_two_cancelling_legs_on_two_accounts() -> None:
    transactions = _transactions(_every_rule_outcome())
    groups: dict[str, list[GoldTransaction]] = {}
    for transaction in transactions:
        if transaction.transfer_group_id is not None:
            assert transaction.transaction_type == "transfer", transaction
            groups.setdefault(transaction.transfer_group_id, []).append(transaction)

    assert len(groups) == 2
    for legs in groups.values():
        assert len(legs) == 2, legs
        assert legs[0].account_id != legs[1].account_id, legs
        assert legs[0].amount + legs[1].amount == Decimal(0), legs


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
    open_items = {i.review_item_id for i in result.classification_review_items()}

    for transaction in transactions:
        line = lineage[transaction.transaction_id]
        if transaction.transaction_type == "unknown":
            assert line.classification_source == "unclassified", line
            assert transaction.transaction_id in involved, transaction
            assert set(line.review_item_ids) <= open_items, line
            assert line.review_item_ids, line
        elif transaction.transaction_type == "transfer":
            assert line.classification_source == "transfer_match", line
            assert line.transfer_evidence is not None, line
            assert line.transfer_evidence.claim_rule_ids, line
        else:
            assert line.classification_source == "rule", line
            assert line.rule_ids, line
