# Copyright 2026 Therkel
"""`gold.build` applies manual decisions, as `classification.md` specifies.

Each test reproduces a scenario of that doc's *Manual Decisions*, numbered as
it numbers them, over the doc's synthetic setup
(`tests/gold/classification_example.py`).
"""

from datetime import date

from budget.gold import GoldResult, GoldTransactionLineage, TransactionType
from budget.gold.decisions import Classify, ClassifyAdjustment
from tests.gold.classification_example import CURRENT, booked, classified


def _types(result: GoldResult) -> dict[str, TransactionType]:
    return {
        t.transaction_id: t.transaction_type
        for t in result.transactions(start_date=date.min, end_date=date.max)
    }


def _lineage(result: GoldResult, transaction_id: str) -> GoldTransactionLineage:
    (line,) = result.transaction_lineage([transaction_id])
    return line


def test_7_a_manual_decision_beats_a_rule_and_lineage_still_names_the_rule() -> None:
    result = classified(
        booked("ikea", CURRENT, date(2026, 2, 7), "-2400.00", "IKEA 551"),
        decisions=[Classify("d-0001", "ikea", "gifts")],
    )

    assert _types(result) == {"ikea": "expense"}
    assert [
        (a.transaction_id, a.category_id)
        for a in result.category_allocations(start_date=date.min, end_date=date.max)
    ] == [("ikea", "gifts")]
    line = _lineage(result, "ikea")
    assert (line.classification_source, line.decision_id, line.rule_ids) == (
        "manual",
        "d-0001",
        ("r-home",),
    )
    assert list(result.classification_review_items()) == []


def test_an_adjustment_decision_gives_an_adjustment_with_the_decisions_reason() -> None:
    result = classified(
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        decisions=[ClassifyAdjustment("d-0005", "netto", "Opening balance fix")],
    )

    assert _types(result) == {"netto": "adjustment"}
    assert (
        list(result.category_allocations(start_date=date.min, end_date=date.max)) == []
    )
    line = _lineage(result, "netto")
    assert (
        line.classification_source,
        line.decision_id,
        line.adjustment_reason,
    ) == ("manual", "d-0005", "Opening balance fix")
