# Copyright 2026 Therkel
"""`gold.build` applies manual decisions, as `classification.md` specifies.

Each test reproduces a scenario of that doc's *Manual Decisions*, numbered as
it numbers them, over the doc's synthetic setup
(`tests/gold/classification_example.py`).
"""

from datetime import date

from budget.gold import (
    GoldResult,
    GoldTransactionLineage,
    TransactionType,
    TransferEvidence,
)
from budget.gold.decisions import (
    Classify,
    ClassifyAdjustment,
    GoldDecision,
    OneSidedTransfer,
    Pair,
)
from tests.gold.classification_example import CURRENT, SAVINGS, booked, classified


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


def test_12_a_pair_decision_settles_competing_legs_and_frees_the_third() -> None:
    result = classified(
        booked("to-savings", CURRENT, date(2026, 3, 5), "-1500.00", "TO SAVINGS"),
        booked("dentist", CURRENT, date(2026, 3, 5), "-1500.00", "DENTIST 7"),
        booked("from-current", SAVINGS, date(2026, 3, 5), "1500.00", "FROM CURRENT"),
        decisions=[Pair("d-0002", ("to-savings", "from-current"))],
    )

    assert _types(result) == {
        "to-savings": "transfer",
        "dentist": "expense",
        "from-current": "transfer",
    }
    groups = {
        t.transaction_id: t.transfer_group_id
        for t in result.transactions(start_date=date.min, end_date=date.max)
    }
    assert groups["to-savings"] is not None
    assert groups["to-savings"] == groups["from-current"]
    assert groups["dentist"] is None
    out = _lineage(result, "to-savings")
    assert (out.classification_source, out.decision_id, out.transfer_evidence) == (
        "manual",
        "d-0002",
        TransferEvidence(
            basis="manual_pair",
            counterpart_account_id=SAVINGS,
            counterpart_transaction_id="from-current",
            date_gap_days=0,
            claim_rule_ids=("r-savings-transfer",),
        ),
    )
    assert _lineage(result, "dentist").classification_source == "rule"
    assert list(result.classification_review_items()) == []


def test_17_a_decision_whose_target_is_missing_is_not_applicable() -> None:
    result = classified(
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        decisions=[Classify("d-0004", "withdrawn-by-bank", "groceries")],
    )

    assert _types(result) == {"netto": "expense"}
    (item,) = result.classification_review_items()
    assert (
        item.kind,
        item.transaction_ids,
        item.rule_ids,
        item.decision_id,
        item.reason,
    ) == ("decision-not-applicable", (), (), "d-0004", "target-missing")


def test_a_pair_missing_one_leg_leaves_the_other_as_if_undecided() -> None:
    result = classified(
        booked("to-savings", CURRENT, date(2026, 2, 16), "-1000.00", "TO SAVINGS"),
        decisions=[Pair("d-0009", ("to-savings", "withdrawn-by-bank"))],
    )

    assert _types(result) == {"to-savings": "unknown"}
    items = {i.kind: i for i in result.classification_review_items()}
    assert items.keys() == {"unmatched-transfer", "decision-not-applicable"}
    assert items["decision-not-applicable"].transaction_ids == ("to-savings",)
    line = _lineage(result, "to-savings")
    assert (line.classification_source, line.decision_id) == ("unclassified", None)
    assert set(line.review_item_ids) == {i.review_item_id for i in items.values()}


def _reasons(result: GoldResult) -> dict[str, str | None]:
    return {i.kind: i.reason for i in result.classification_review_items()}


def test_a_category_decision_on_a_zero_amount_is_not_applicable() -> None:
    result = classified(
        booked("netto", CURRENT, date(2026, 2, 2), "0.00", "NETTO 0412"),
        decisions=[Classify("d-0006", "netto", "groceries")],
    )

    assert _types(result) == {"netto": "unknown"}
    assert _reasons(result) == {
        "sign-mismatch": None,
        "decision-not-applicable": "zero-amount",
    }


def _before_savings_history(*decisions: GoldDecision) -> GoldResult:
    """Scenario 16: a transfer into savings before its managed period starts."""
    return classified(
        booked("to-savings", CURRENT, date(2025, 12, 15), "-10000.00", "TO SAVINGS"),
        # joint-savings' first booked transaction starts its managed period.
        booked("interest", SAVINGS, date(2026, 1, 31), "1.00", "INTEREST"),
        decisions=decisions,
    )


def test_16_a_one_sided_transfer_has_no_group_and_names_its_counterpart() -> None:
    result = _before_savings_history(OneSidedTransfer("d-0003", "to-savings", SAVINGS))

    (leg,) = [
        t
        for t in result.transactions(start_date=date.min, end_date=date.max)
        if t.transaction_id == "to-savings"
    ]
    assert (leg.transaction_type, leg.transfer_group_id) == ("transfer", None)
    line = _lineage(result, "to-savings")
    assert (line.classification_source, line.decision_id, line.transfer_evidence) == (
        "manual",
        "d-0003",
        TransferEvidence(
            basis="one_sided",
            counterpart_account_id=SAVINGS,
            counterpart_transaction_id=None,
            date_gap_days=None,
            claim_rule_ids=("r-savings-transfer",),
        ),
    )
    assert list(result.classification_review_items()) == []
