# Copyright 2026 Therkel
"""`gold.build` classifies by rules, as `classification.md` specifies.

Each test reproduces a rule-only scenario of that doc, numbered as it numbers
them, over the doc's synthetic setup (`tests/gold/classification_example.py`).
"""

from datetime import date
from decimal import Decimal

from budget.gold import GoldCategoryAllocation, GoldResult, TransactionType
from budget.inputs import AssignCategory, Rule, RuleConditions
from tests.gold.classification_example import CURRENT, SAVINGS, booked, classified


def _types(result: GoldResult) -> dict[str, TransactionType]:
    return {
        t.transaction_id: t.transaction_type
        for t in result.transactions(start_date=date.min, end_date=date.max)
    }


def _allocations(result: GoldResult) -> list[GoldCategoryAllocation]:
    return list(result.category_allocations(start_date=date.min, end_date=date.max))


def test_1_a_rule_assigns_an_expense_its_whole_amount_in_one_category() -> None:
    result = classified(
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412")
    )

    assert _types(result) == {"netto": "expense"}
    assert _allocations(result) == [
        GoldCategoryAllocation(
            allocation_id="netto/groceries",
            transaction_id="netto",
            account_id=CURRENT,
            transaction_date=date(2026, 2, 2),
            category_id="groceries",
            amount=Decimal("-640.00"),
        )
    ]


def test_2_a_positive_amount_in_an_expense_category_is_a_refund_netting_it() -> None:
    result = classified(
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        booked("return", CURRENT, date(2026, 2, 12), "120.00", "NETTO 0412"),
    )

    assert _types(result) == {"netto": "expense", "return": "refund"}
    groceries = [a for a in _allocations(result) if a.category_id == "groceries"]
    assert sum(a.amount for a in groceries) == Decimal("-520.00")


def test_4_equal_priority_rules_that_disagree_leave_a_rule_conflict() -> None:
    # r-mobilepay (starts with MOBILEPAY) says eating-out; r-netto (contains
    # NETTO) says groceries. Both have priority 0.
    result = classified(
        booked("conflict", CURRENT, date(2026, 2, 20), "-85.00", "MOBILEPAY NETTO")
    )

    assert _types(result) == {"conflict": "unknown"}
    assert _allocations(result) == []
    assert [
        (i.kind, i.transaction_ids, i.rule_ids, i.decision_id, i.reason)
        for i in result.classification_review_items()
    ] == [("rule-conflict", ("conflict",), ("r-mobilepay", "r-netto"), None, None)]


def test_6_and_15_an_income_category_is_income_in_and_a_refund_out() -> None:
    result = classified(
        booked("from-bo", CURRENT, date(2026, 2, 1), "4000.00", "FROM BO"),
        booked("interest", SAVINGS, date(2026, 3, 31), "-3.50", "INTEREST ADJ"),
    )

    assert _types(result) == {"from-bo": "income", "interest": "refund"}
    assert {(a.transaction_id, a.category_id) for a in _allocations(result)} == {
        ("from-bo", "contribution"),
        ("interest", "interest"),
    }


def test_a_transaction_no_rule_matches_is_unknown_with_an_unclassified_item() -> None:
    result = classified(booked("cash", CURRENT, date(2026, 2, 3), "-200.00", "ATM 17"))

    assert _types(result) == {"cash": "unknown"}
    assert _allocations(result) == []
    # The review item's identifier has a test of its own.
    assert [
        (i.kind, i.transaction_ids, i.rule_ids, i.decision_id, i.reason)
        for i in result.classification_review_items()
    ] == [("unclassified", ("cash",), (), None, None)]


def test_a_rule_matches_text_that_starts_with_its_pattern_in_any_case() -> None:
    # r-mobilepay: text starts with MOBILEPAY, assigns eating-out.
    result = classified(
        booked("cafe", CURRENT, date(2026, 2, 21), "-85.00", "MobilePay Cafe Luna"),
        booked("via", CURRENT, date(2026, 2, 22), "-40.00", "CAFE VIA MOBILEPAY"),
    )

    assert _types(result) == {"cafe": "expense", "via": "unknown"}
    assert [(a.transaction_id, a.category_id) for a in _allocations(result)] == [
        ("cafe", "eating-out")
    ]


def test_a_rule_matches_only_text_that_meets_every_description_condition() -> None:
    luna = RuleConditions(
        description_contains=("LUNA",), description_starts_with=("MOBILEPAY",)
    )
    rules = {"r-luna": Rule("r-luna", 0, luna, AssignCategory("eating-out"))}

    result = classified(
        booked("both", CURRENT, date(2026, 2, 21), "-85.00", "MobilePay Cafe Luna"),
        booked("prefix", CURRENT, date(2026, 2, 22), "-40.00", "MobilePay Netto"),
        booked("text", CURRENT, date(2026, 2, 23), "-60.00", "Cafe Luna"),
        rules=rules,
    )

    assert _types(result) == {"both": "expense", "prefix": "unknown", "text": "unknown"}


def test_a_rule_matches_text_its_regex_finds_in_any_case() -> None:
    store = RuleConditions(description_regex=(r"netto \d{4}",))
    rules = {
        "r-netto-store": Rule("r-netto-store", 0, store, AssignCategory("groceries"))
    }

    result = classified(
        booked("store", CURRENT, date(2026, 2, 24), "-320.00", "Dankort NETTO 0412"),
        booked("online", CURRENT, date(2026, 2, 25), "-150.00", "NETTO ONLINE"),
        rules=rules,
    )

    assert _types(result) == {"store": "expense", "online": "unknown"}
