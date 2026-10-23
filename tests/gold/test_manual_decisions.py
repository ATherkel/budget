# Copyright 2026 Therkel
"""`gold.build` applies manual decisions, as `classification.md` specifies.

Each test reproduces a scenario of that doc's *Manual Decisions*, numbered as
it numbers them, over the doc's synthetic setup
(`tests/gold/classification_example.py`).
"""

from dataclasses import replace
from datetime import date

import pytest

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
from budget.inputs import ConfigurationError
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


def _not_applicable(result: GoldResult) -> tuple[tuple[str, ...], str | None]:
    (item,) = [
        i
        for i in result.classification_review_items()
        if i.kind == "decision-not-applicable"
    ]
    return item.transaction_ids, item.reason


def test_a_pair_whose_amounts_do_not_cancel_is_not_applicable() -> None:
    # A transfer that lost a fee never pairs (classification.md, issue #47).
    result = classified(
        booked("to-savings", CURRENT, date(2026, 2, 16), "-1000.00", "TO SAVINGS"),
        booked("from-current", SAVINGS, date(2026, 2, 16), "995.00", "FROM CURRENT"),
        decisions=[Pair("d-0010", ("to-savings", "from-current"))],
    )

    assert _types(result) == {"to-savings": "unknown", "from-current": "unknown"}
    assert _not_applicable(result) == (
        ("to-savings", "from-current"),
        "amounts-do-not-cancel",
    )


def test_a_pair_on_one_account_is_not_applicable() -> None:
    result = classified(
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        booked("return", CURRENT, date(2026, 2, 2), "640.00", "NETTO 0412"),
        decisions=[Pair("d-0011", ("netto", "return"))],
    )

    assert _types(result) == {"netto": "expense", "return": "refund"}
    assert _not_applicable(result) == (("netto", "return"), "same-account")


def test_18_every_decision_naming_a_missing_category_refuses_the_build() -> None:
    netto = booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412")

    with pytest.raises(ConfigurationError) as refused:
        classified(
            netto,
            decisions=[
                Classify("d-0012", "netto", "food-out"),
                Classify("d-0013", "ikea", "furniture"),
            ],
        )

    first, second = refused.value.problems
    assert ("d-0012" in first, "food-out" in first) == (True, True)
    assert ("d-0013" in second, "furniture" in second) == (True, True)


def test_a_one_sided_counterpart_missing_from_the_registry_refuses_the_build() -> None:
    leg = booked("to-bo", CURRENT, date(2026, 2, 1), "-4000.00", "BUDGET TO BO")

    with pytest.raises(ConfigurationError) as refused:
        classified(leg, decisions=[OneSidedTransfer("d-0014", "to-bo", "bo-current")])

    (problem,) = refused.value.problems
    assert ("d-0014" in problem, "bo-current" in problem) == (True, True)


def test_the_classification_version_fingerprints_the_decisions_too() -> None:
    def version(*decisions: GoldDecision) -> str:
        result = classified(
            booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
            booked("ikea", CURRENT, date(2026, 2, 7), "-2400.00", "IKEA 551"),
            decisions=decisions,
        )
        return _lineage(result, "netto").classification_version

    gifts = Classify("d-0001", "ikea", "gifts")
    assert version(gifts) == version(gifts)
    # The decision is on ikea, yet every transaction's version changes with it.
    assert (
        len({version(), version(gifts), version(replace(gifts, category_id="rent"))})
        == 3
    )


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


def test_a_one_sided_transfer_inside_the_counterparts_period_is_not_applicable() -> (
    None
):
    # The managed period runs by month: joint-savings' first booking on
    # 2026-01-31 starts it on 2026-01-01, so 2026-01-15 falls inside it.
    result = classified(
        booked("to-savings", CURRENT, date(2026, 1, 15), "-10000.00", "TO SAVINGS"),
        booked("interest", SAVINGS, date(2026, 1, 31), "1.00", "INTEREST"),
        decisions=[OneSidedTransfer("d-0003", "to-savings", SAVINGS)],
    )

    assert _types(result)["to-savings"] == "unknown"
    assert _not_applicable(result) == (("to-savings",), "inside-managed-period")


def _every_decision_outcome() -> GoldResult:
    """Every decision kind, applicable and not, beside rules and matching."""
    return classified(
        booked("ikea", CURRENT, date(2026, 2, 7), "-2400.00", "IKEA 551"),
        booked("fix", CURRENT, date(2026, 2, 9), "-7.25", "ATM 17"),
        booked("to-savings", CURRENT, date(2026, 3, 5), "-1500.00", "TO SAVINGS"),
        booked("dentist", CURRENT, date(2026, 3, 5), "-1500.00", "DENTIST 7"),
        booked("from-current", SAVINGS, date(2026, 3, 5), "1500.00", "FROM CURRENT"),
        booked("early", CURRENT, date(2025, 12, 15), "-10000.00", "TO SAVINGS"),
        booked("inside", CURRENT, date(2026, 3, 20), "-300.00", "TO SAVINGS"),
        booked("zero", CURRENT, date(2026, 2, 2), "0.00", "NETTO 0412"),
        booked("fee-out", CURRENT, date(2026, 2, 16), "-1000.00", "TO SAVINGS"),
        booked("fee-in", SAVINGS, date(2026, 2, 16), "995.00", "FROM CURRENT"),
        booked("netto", CURRENT, date(2026, 2, 2), "-640.00", "NETTO 0412"),
        booked("return", CURRENT, date(2026, 2, 2), "640.00", "NETTO 0412"),
        decisions=[
            Classify("d-0001", "ikea", "gifts"),
            ClassifyAdjustment("d-0005", "fix", "Opening balance fix"),
            Pair("d-0002", ("to-savings", "from-current")),
            OneSidedTransfer("d-0003", "early", SAVINGS),
            OneSidedTransfer("d-0015", "inside", SAVINGS),
            Classify("d-0004", "withdrawn-by-bank", "groceries"),
            Classify("d-0006", "zero", "groceries"),
            Pair("d-0010", ("fee-out", "fee-in")),
            Pair("d-0011", ("netto", "return")),
        ],
    )


def test_every_not_applicable_reason_is_exercised() -> None:
    reasons = {
        i.reason
        for i in _every_decision_outcome().classification_review_items()
        if i.kind == "decision-not-applicable"
    }

    assert reasons == {
        "target-missing",
        "zero-amount",
        "amounts-do-not-cancel",
        "same-account",
        "inside-managed-period",
    }


def test_invariant_17_a_groupless_transfer_is_one_sided_outside_its_counterpart() -> (
    None
):
    result = _every_decision_outcome()
    groupless = [
        t
        for t in result.transactions(start_date=date.min, end_date=date.max)
        if t.transaction_type == "transfer" and t.transfer_group_id is None
    ]

    assert [t.transaction_id for t in groupless] == ["early"]
    evidence = _lineage(result, "early").transfer_evidence
    assert evidence is not None
    # joint-savings' managed period starts in 2026-02, its first booking.
    assert (evidence.basis, evidence.counterpart_account_id) == ("one_sided", SAVINGS)


def test_invariant_19_every_type_traces_to_its_source_and_unknown_to_an_item() -> None:
    result = _every_decision_outcome()
    transactions = list(result.transactions(start_date=date.min, end_date=date.max))
    lineage = {
        line.transaction_id: line
        for line in result.transaction_lineage([t.transaction_id for t in transactions])
    }
    open_items = {i.review_item_id for i in result.classification_review_items()}

    for transaction in transactions:
        line = lineage[transaction.transaction_id]
        if transaction.transaction_type == "unknown":
            assert line.classification_source == "unclassified", line
            assert line.review_item_ids, line
            assert set(line.review_item_ids) <= open_items, line
        elif line.classification_source == "manual":
            assert line.decision_id is not None, line
        else:
            assert line.decision_id is None, line
            assert line.classification_source in {"rule", "transfer_match"}, line
    assert {
        tid for tid, line in lineage.items() if line.classification_source == "manual"
    } == {"ikea", "fix", "to-savings", "from-current", "early"}
