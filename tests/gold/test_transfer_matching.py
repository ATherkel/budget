# Copyright 2026 Therkel
"""`gold.build` pairs transfer legs, as `classification.md` specifies.

Each test reproduces a scenario of that doc's *Transfer Matching*, numbered as
it numbers them, over the doc's synthetic setup
(`tests/gold/classification_example.py`).
"""

from dataclasses import replace
from datetime import date

from budget.gold import (
    ClassificationSource,
    GoldResult,
    GoldTransaction,
    TransactionType,
    TransferEvidence,
)
from budget.silver import Transaction
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


def _unmatched(result: GoldResult) -> list[tuple[tuple[str, ...], str | None]]:
    return [
        (i.transaction_ids, i.reason)
        for i in result.classification_review_items()
        if i.kind == "unmatched-transfer"
    ]


def test_13_a_claim_past_the_counterparts_latest_import_may_be_waiting() -> None:
    # The latest joint-savings transaction is from before the leg's date + 3.
    result = classified(
        booked("to-savings", CURRENT, date(2026, 4, 29), "-800.00", "TO SAVINGS"),
        booked("interest", SAVINGS, date(2026, 4, 20), "12.00", "INTEREST"),
        booked("cafe", ANNA, date(2026, 5, 10), "-85.00", "MOBILEPAY CARL"),
    )

    assert _types(result)["to-savings"] == "unknown"
    assert _unmatched(result) == [(("to-savings",), "counterpart-may-not-be-imported")]


def test_an_account_with_no_transactions_also_may_be_waiting() -> None:
    # The hint cannot tell a quiet account from one not imported yet.
    result = classified(
        booked("to-savings", CURRENT, date(2026, 2, 16), "-1000.00", "TO SAVINGS"),
        booked("interest", SAVINGS, date(2026, 2, 27), "12.00", "INTEREST"),
    )

    assert _unmatched(result) == [(("to-savings",), "counterpart-may-not-be-imported")]


def test_a_counterpart_transaction_exactly_3_days_later_rules_out_waiting() -> None:
    # "on or after the leg's transaction date plus 3 days" is inclusive.
    result = classified(
        booked("to-savings", CURRENT, date(2026, 2, 16), "-1000.00", "TO SAVINGS"),
        booked("interest", SAVINGS, date(2026, 2, 19), "12.00", "INTEREST"),
        booked("cafe", ANNA, date(2026, 2, 19), "-85.00", "MOBILEPAY CARL"),
    )

    assert _unmatched(result) == [(("to-savings",), "no-candidate")]


def _transactions(result: GoldResult) -> dict[str, GoldTransaction]:
    return {
        t.transaction_id: t
        for t in result.transactions(start_date=date.min, end_date=date.max)
    }


type _Line = tuple[
    ClassificationSource, tuple[str, ...], TransferEvidence | None, tuple[str, ...]
]


def _evidence(result: GoldResult, *transaction_ids: str) -> dict[str, _Line]:
    return {
        line.transaction_id: (
            line.classification_source,
            line.rule_ids,
            line.transfer_evidence,
            line.review_item_ids,
        )
        for line in result.transaction_lineage(transaction_ids)
    }


def test_8_same_day_legs_that_cancel_are_one_transfer() -> None:
    result = classified(
        booked("out", CURRENT, date(2026, 1, 20), "-3000.00", "TO SAVINGS"),
        booked("in", SAVINGS, date(2026, 1, 20), "3000.00", "FROM CURRENT"),
    )
    transactions = _transactions(result)

    assert _types(result) == {"out": "transfer", "in": "transfer"}
    group = transactions["out"].transfer_group_id
    assert group is not None
    assert transactions["in"].transfer_group_id == group
    assert (
        list(result.category_allocations(start_date=date.min, end_date=date.max)) == []
    )
    assert list(result.classification_review_items()) == []
    claim = ("r-savings-transfer",)
    assert _evidence(result, "out", "in") == {
        "out": (
            "transfer_match",
            claim,
            TransferEvidence("same_day", SAVINGS, "in", 0, claim),
            (),
        ),
        "in": (
            "transfer_match",
            claim,
            TransferEvidence("same_day", CURRENT, "out", 0, claim),
            (),
        ),
    }


def test_13_the_next_import_pairs_the_waiting_leg_and_drops_its_item() -> None:
    waiting = booked("to-savings", CURRENT, date(2026, 4, 29), "-800.00", "TO SAVINGS")
    arrived = booked(
        "from-current", SAVINGS, date(2026, 4, 29), "800.00", "FROM CURRENT"
    )

    result = classified(waiting, arrived)

    assert _types(result) == {"to-savings": "transfer", "from-current": "transfer"}
    assert _unmatched(result) == []


def test_9_a_pair_3_days_apart_spans_a_month_boundary_on_date_gap() -> None:
    result = classified(
        booked("out", CURRENT, date(2026, 1, 30), "-5000.00", "TO SAVINGS"),
        booked("in", SAVINGS, date(2026, 2, 2), "5000.00", "FROM CURRENT"),
    )
    claim = ("r-savings-transfer",)

    assert _types(result) == {"out": "transfer", "in": "transfer"}
    assert [
        t.transaction_id
        for t in result.transactions(
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31)
        )
    ] == ["out"]
    assert [
        t.transaction_id
        for t in result.transactions(
            start_date=date(2026, 2, 1), end_date=date(2026, 2, 28)
        )
    ] == ["in"]
    assert (
        list(result.category_allocations(start_date=date.min, end_date=date.max)) == []
    )
    assert _evidence(result, "out")["out"][2] == TransferEvidence(
        "date_gap", SAVINGS, "in", 3, claim
    )


def test_legs_4_days_apart_are_not_candidates() -> None:
    result = classified(
        booked("out", CURRENT, date(2026, 1, 29), "-5000.00", "TO SAVINGS"),
        booked("in", SAVINGS, date(2026, 2, 2), "5000.00", "FROM CURRENT"),
    )

    assert _types(result) == {"out": "unknown", "in": "unknown"}
    assert sorted(ids for ids, _ in _unmatched(result)) == [("in",), ("out",)]


def test_10_a_coincidence_without_a_claim_is_not_a_transfer() -> None:
    result = classified(
        booked("ikea", CURRENT, date(2026, 3, 10), "-250.00", "IKEA 551"),
        booked("carl", ANNA, date(2026, 3, 10), "250.00", "MOBILEPAY CARL"),
    )

    assert _types(result) == {"ikea": "expense", "carl": "refund"}


def _groups(result: GoldResult) -> set[frozenset[str]]:
    by_group: dict[str, set[str]] = {}
    for t in _transactions(result).values():
        if t.transfer_group_id is not None:
            by_group.setdefault(t.transfer_group_id, set()).add(t.transaction_id)
    return {frozenset(ids) for ids in by_group.values()}


def _nth(
    transaction_id: str, account_id: str, text: str, amount: str, n: int
) -> Transaction:
    leg = booked(transaction_id, account_id, date(2026, 3, 2), amount, text)
    return replace(leg, day_sequence=n)


def test_11_repeated_legs_pair_in_account_sequence_order() -> None:
    # The ids run against the booked order on joint-current, so pairing by id
    # would join other legs.
    result = classified(
        _nth("a1", ANNA, "BUDGET JOINT", "-2000.00", 1),
        _nth("a2", ANNA, "BUDGET JOINT", "-2000.00", 2),
        _nth("c2", CURRENT, "BUDGET FROM ANNA", "2000.00", 1),
        _nth("c1", CURRENT, "BUDGET FROM ANNA", "2000.00", 2),
    )
    claim = ("r-budget-transfer",)

    assert set(_types(result).values()) == {"transfer"}
    assert _groups(result) == {frozenset({"a1", "c2"}), frozenset({"a2", "c1"})}
    assert _evidence(result, "a1")["a1"][2] == TransferEvidence(
        "repeated_legs", CURRENT, "c2", 0, claim
    )
    assert list(result.classification_review_items()) == []
