# Copyright 2026 Therkel
"""`gold.build` pairs transfer legs, as `classification.md` specifies.

Each test reproduces a scenario of that doc's *Transfer Matching*, numbered as
it numbers them, over the doc's synthetic setup
(`tests/gold/classification_example.py`).
"""

from datetime import date

from budget.gold import GoldResult, TransactionType
from tests.gold.classification_example import ANNA, CURRENT, SAVINGS, booked, classified


def _types(result: GoldResult) -> dict[str, TransactionType]:
    return {
        t.transaction_id: t.transaction_type
        for t in result.transactions(start_date=date.min, end_date=date.max)
    }


def test_14_a_claim_with_no_candidate_is_unknown_with_an_unmatched_item() -> None:
    # Both other accounts have later transactions, and none is +1,000.00.
    result = classified(
        booked("to-savings", CURRENT, date(2026, 2, 16), "-1000.00", "TO SAVINGS"),
        booked("interest", SAVINGS, date(2026, 2, 27), "12.00", "INTEREST"),
        booked("cafe", ANNA, date(2026, 2, 27), "-85.00", "MOBILEPAY CARL"),
    )
    items = [
        i for i in result.classification_review_items() if i.kind != "unclassified"
    ]
    (line,) = result.transaction_lineage(["to-savings"])

    assert _types(result)["to-savings"] == "unknown"
    assert [(i.kind, i.transaction_ids, i.rule_ids, i.reason) for i in items] == [
        ("unmatched-transfer", ("to-savings",), ("r-savings-transfer",), "no-candidate")
    ]
    assert line.review_item_ids == (items[0].review_item_id,)
