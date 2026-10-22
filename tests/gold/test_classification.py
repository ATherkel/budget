# Copyright 2026 Therkel
"""`gold.build` classifies by rules, as `classification.md` specifies.

Each test reproduces a rule-only scenario of that doc, numbered as it numbers
them, over the doc's synthetic setup (`tests/gold/classification_example.py`).
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.gold import GoldCategoryAllocation, GoldResult, TransactionType
from budget.inputs import (
    AssignAdjustment,
    AssignCategory,
    ConfigurationSnapshot,
    Rule,
    RuleConditions,
)
from tests.gold.classification_example import (
    ACCOUNTS,
    CURRENT,
    RULES,
    SAVINGS,
    TAXONOMY,
    booked,
    classified,
)


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


def test_3_a_bank_label_classifies_only_through_a_rule_that_tests_it() -> None:
    # r-bank-groceries (priority -10): bank category label is Groceries.
    foetex = booked("foetex", CURRENT, date(2026, 2, 14), "-310.00", "FOETEX 88")

    result = classified(replace(foetex, bank_category="Groceries"))

    assert _types(result) == {"foetex": "expense"}
    assert [(a.transaction_id, a.category_id) for a in _allocations(result)] == [
        ("foetex", "groceries")
    ]


def test_a_rule_matches_only_a_transaction_that_meets_text_and_label() -> None:
    netto = RuleConditions(description_contains=("NETTO",), bank_category="Groceries")
    rules = {
        "r-netto-shop": Rule("r-netto-shop", 0, netto, AssignCategory("groceries"))
    }
    shop = booked("shop", CURRENT, date(2026, 2, 15), "-90.00", "NETTO 0412")
    other = booked("other", CURRENT, date(2026, 2, 16), "-70.00", "FOETEX 88")

    result = classified(
        replace(shop, bank_category="Groceries"),
        replace(shop, transaction_id="text", bank_category="Leisure"),
        replace(other, bank_category="Groceries"),
        rules=rules,
    )

    assert _types(result) == {"shop": "expense", "text": "unknown", "other": "unknown"}


def test_a_rule_matches_a_bank_label_in_any_case() -> None:
    # r-bank-groceries: bank category label is Groceries.
    foetex = booked("foetex", CURRENT, date(2026, 2, 14), "-310.00", "FOETEX 88")

    result = classified(replace(foetex, bank_category="GROCERIES"))

    assert _types(result) == {"foetex": "expense"}


def test_a_rule_matches_only_a_transaction_on_its_account() -> None:
    # r-interest: account is joint-savings and text contains INTEREST.
    result = classified(
        booked("savings", SAVINGS, date(2026, 3, 31), "12.00", "INTEREST"),
        booked("current", CURRENT, date(2026, 3, 31), "12.00", "INTEREST"),
    )

    assert _types(result) == {"savings": "income", "current": "unknown"}


def test_a_rule_matches_only_an_amount_of_its_sign() -> None:
    spend = RuleConditions(description_contains=("NETTO",), amount_sign="negative")
    rules = {"r-spend": Rule("r-spend", 0, spend, AssignCategory("groceries"))}

    result = classified(
        booked("out", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        booked("in", CURRENT, date(2026, 2, 12), "120.00", "NETTO 0412"),
        booked("zero", CURRENT, date(2026, 2, 13), "0.00", "NETTO 0412"),
        rules=rules,
    )

    assert _types(result) == {"out": "expense", "in": "unknown", "zero": "unknown"}
    assert [(a.transaction_id, a.category_id) for a in _allocations(result)] == [
        ("out", "groceries")
    ]


def test_a_rule_matches_an_amount_in_its_inclusive_range() -> None:
    # Like r-furniture in operations.md: an IKEA purchase from -5000.00 to
    # -1000.00 outranks r-home. The setup has no furniture category, so gifts
    # stands in for it.
    big = RuleConditions(
        description_contains=("IKEA",),
        amount_min=Decimal("-5000.00"),
        amount_max=Decimal("-1000.00"),
    )
    rules = {
        **RULES,
        "r-furniture": Rule("r-furniture", 10, big, AssignCategory("gifts")),
    }

    result = classified(
        booked("sofa", CURRENT, date(2026, 2, 7), "-2400.00", "IKEA 551"),
        booked("edge", CURRENT, date(2026, 2, 8), "-1000.00", "IKEA 551"),
        booked("floor", CURRENT, date(2026, 2, 9), "-5000.00", "IKEA 551"),
        booked("lamp", CURRENT, date(2026, 2, 10), "-400.00", "IKEA 551"),
        booked("kitchen", CURRENT, date(2026, 2, 11), "-5000.01", "IKEA 551"),
        rules=rules,
    )

    assert {(a.transaction_id, a.category_id) for a in _allocations(result)} == {
        ("sofa", "gifts"),
        ("edge", "gifts"),
        ("floor", "gifts"),
        ("lamp", "household-goods"),
        ("kitchen", "household-goods"),
    }


def test_a_rule_matches_a_date_in_its_inclusive_range() -> None:
    february = RuleConditions(
        description_contains=("NETTO",),
        date_from=date(2026, 2, 1),
        date_to=date(2026, 2, 28),
    )
    rules = {"r-feb": Rule("r-feb", 0, february, AssignCategory("groceries"))}

    result = classified(
        booked("first", CURRENT, date(2026, 2, 1), "-10.00", "NETTO 0412"),
        booked("last", CURRENT, date(2026, 2, 28), "-10.00", "NETTO 0412"),
        booked("before", CURRENT, date(2026, 1, 31), "-10.00", "NETTO 0412"),
        booked("after", CURRENT, date(2026, 3, 1), "-10.00", "NETTO 0412"),
        rules=rules,
    )

    assert _types(result) == {
        "first": "expense",
        "last": "expense",
        "before": "unknown",
        "after": "unknown",
    }


def test_a_rule_matches_a_bank_subcategory_in_any_case() -> None:
    bakery = RuleConditions(bank_subcategory="Bakery")
    rules = {"r-bakery": Rule("r-bakery", 0, bakery, AssignCategory("eating-out"))}
    bread = booked("bread", CURRENT, date(2026, 2, 17), "-45.00", "LAGKAGEHUSET")

    result = classified(
        replace(bread, bank_subcategory="BAKERY"),
        replace(bread, transaction_id="meat", bank_subcategory="Butcher"),
        replace(bread, transaction_id="none"),
        rules=rules,
    )

    assert _types(result) == {"bread": "expense", "meat": "unknown", "none": "unknown"}


def test_a_category_rule_on_a_zero_amount_leaves_a_sign_mismatch() -> None:
    # classification.md, after the scenarios: zero-amount INTEREST ADJ.
    result = classified(
        booked("zero", SAVINGS, date(2026, 3, 31), "0.00", "INTEREST ADJ")
    )

    assert _types(result) == {"zero": "unknown"}
    assert _allocations(result) == []
    assert [
        (i.kind, i.transaction_ids, i.rule_ids, i.decision_id, i.reason)
        for i in result.classification_review_items()
    ] == [("sign-mismatch", ("zero",), ("r-interest",), None, None)]


def test_an_adjustment_rule_gives_an_adjustment_with_no_category() -> None:
    # As r-interest-correction in operations.md.
    correction = RuleConditions(account=SAVINGS, description_starts_with=("RENTEKORR",))
    outcome = AssignAdjustment("Bank's interest correction")
    rules = {"r-correction": Rule("r-correction", 0, correction, outcome)}

    result = classified(
        booked("fix", SAVINGS, date(2026, 3, 31), "-7.25", "RENTEKORR 2026"),
        rules=rules,
    )

    assert _types(result) == {"fix": "adjustment"}
    assert _allocations(result) == []
    assert list(result.classification_review_items()) == []


def test_lineage_names_the_rules_and_review_items_behind_each_type() -> None:
    result = classified(
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        booked("cash", CURRENT, date(2026, 2, 3), "-200.00", "ATM 17"),
        booked("conflict", CURRENT, date(2026, 2, 20), "-85.00", "MOBILEPAY NETTO"),
    )
    version = ConfigurationSnapshot(
        accounts=ACCOUNTS, taxonomy=TAXONOMY, rules=RULES
    ).fingerprint
    items = {
        i.transaction_ids: i.review_item_id
        for i in result.classification_review_items()
    }

    lineage = {
        line.transaction_id: line
        for line in result.transaction_lineage(["netto", "cash", "conflict"])
    }

    assert {
        tid: (
            line.silver_transaction_id,
            line.classification_source,
            line.rule_ids,
            line.decision_id,
            line.classification_version,
            line.transfer_evidence,
            line.review_item_ids,
        )
        for tid, line in lineage.items()
    } == {
        "netto": ("netto", "rule", ("r-netto",), None, version, None, ()),
        "cash": ("cash", "unclassified", (), None, version, None, (items[("cash",)],)),
        "conflict": (
            "conflict",
            "unclassified",
            ("r-mobilepay", "r-netto"),
            None,
            version,
            None,
            (items[("conflict",)],),
        ),
    }


def test_a_rule_that_sets_no_condition_matches_no_transaction() -> None:
    rules = {"r-empty": Rule("r-empty", 0, RuleConditions(), AssignCategory("gifts"))}

    result = classified(
        booked("cash", CURRENT, date(2026, 2, 3), "-200.00", "ATM 17"), rules=rules
    )

    assert _types(result) == {"cash": "unknown"}


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


def test_4_a_rule_conflict_is_the_same_whatever_order_the_rules_are_in() -> None:
    # File order never matters (classification.md, Priority and conflicts).
    conflict = booked(
        "conflict", CURRENT, date(2026, 2, 20), "-85.00", "MOBILEPAY NETTO"
    )
    reversed_rules = dict(reversed(list(RULES.items())))

    as_written = classified(conflict)
    as_reversed = classified(conflict, rules=reversed_rules)

    assert list(as_reversed.classification_review_items()) == list(
        as_written.classification_review_items()
    )


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
