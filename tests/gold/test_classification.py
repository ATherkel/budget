# Copyright 2026 Therkel
"""`gold.build` classifies by rules, as `classification.md` specifies.

Each test reproduces a rule-only scenario of that doc, numbered as it numbers
them, over the doc's synthetic setup (`tests/gold/classification_example.py`).
"""

from datetime import date
from decimal import Decimal

from budget.gold import GoldCategoryAllocation, GoldResult, TransactionType
from tests.gold.classification_example import CURRENT, booked, classified


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
