# Copyright 2026 Therkel
"""Dropped transactions, *withdrawn* and *same transaction* (#95, ADR-017).

Issue #5's scenarios 7, 9 and 13. Each dropped transaction raises its own
review item, following issue #80's option A while that issue is open.
Opening balance 1000,00 throughout.
"""

from datetime import date
from decimal import Decimal

from budget.silver import ReviewItem, SameTransaction, SilverResult, Withdrawn
from tests.silver.exports import (
    ACCOUNT,
    build_from,
    export,
    identity,
    review_item_id,
    row,
)

MARCH_3 = date(2026, 3, 3)
MARCH_5 = date(2026, 3, 5)
SECOND_COFFEE = identity(MARCH_3, "-30.00", "KAFFE", 2)

TWO_COFFEES = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        row("03.03.2026", "KAFFE", "-30,00", "895,00"),
        row("05.03.2026", "BOG", "-25,00", "870,00"),
    ],
    run_id="run-a",
    exported_on=date(2026, 3, 6),
)
# The bank shows one coffee on 3 March; its balances agree with its own rows.
ONE_COFFEE = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        row("05.03.2026", "BOG", "-25,00", "900,00"),
    ],
    run_id="run-b",
    exported_on=date(2026, 3, 9),
)


def _statuses(result: SilverResult) -> dict[str, str]:
    return {r.import_run_id: r.status for r in result.import_run_results}


def _dropped_item(
    transaction_id: str, day: date, resolved_by: str | None
) -> ReviewItem:
    return ReviewItem(
        review_item_id=review_item_id("dropped-transactions", "run-b", transaction_id),
        kind="dropped-transactions",
        account_id=ACCOUNT,
        date_from=day,
        date_to=day,
        payload_ids=("payload-run-b", "payload-run-a"),
        resolved_by=resolved_by,
        transaction_id=transaction_id,
    )


def test_fewer_repeats_quarantine_the_run_and_keep_the_higher_count() -> None:
    result = build_from(TWO_COFFEES, ONE_COFFEE)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "quarantined"}
    assert result.transactions == build_from(TWO_COFFEES).transactions
    assert result.review_items == (_dropped_item(SECOND_COFFEE, MARCH_3, None),)


def test_withdrawn_admits_the_run_and_removes_the_transaction() -> None:
    withdrawn = Withdrawn(decision_id="d-0001", transaction_id=SECOND_COFFEE)

    result = build_from(TWO_COFFEES, ONE_COFFEE, decisions=[withdrawn])

    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}
    assert result.review_items == (_dropped_item(SECOND_COFFEE, MARCH_3, "d-0001"),)
    coffees = [t for t in result.transactions if t.description == "KAFFE"]
    assert [(t.occurrence, t.balance) for t in coffees] == [(1, Decimal("925.00"))]
    assert SECOND_COFFEE not in {e.transaction_id for e in result.transaction_evidence}


def test_a_reworded_transaction_is_dropped_not_a_disagreement() -> None:
    before = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("05.03.2026", "REMA", "-120,00", "835,00"),
        ],
        run_id="run-a",
        exported_on=date(2026, 3, 6),
    )
    reworded = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("05.03.2026", "REMA 1000", "-120,00", "835,00"),
            row("08.03.2026", "LØN", "500,00", "1.335,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 9),
    )
    rema = identity(MARCH_5, "-120.00", "REMA", 1)

    quarantined = build_from(before, reworded)
    same = SameTransaction(
        decision_id="d-0002",
        transaction_id=rema,
        payload_id=reworded.run.payload_id,
        record_ordinal=2,
    )
    admitted = build_from(before, reworded, decisions=[same])

    assert _statuses(quarantined) == {"run-a": "accepted", "run-b": "quarantined"}
    assert [i.kind for i in quarantined.review_items] == ["dropped-transactions"]
    assert _statuses(admitted) == {"run-a": "accepted", "run-b": "accepted"}
    assert [(t.description, t.transaction_id) for t in admitted.transactions] == [
        ("NETTO", identity(date(2026, 3, 1), "-45.00", "NETTO", 1)),
        ("REMA", rema),
        ("LØN", identity(date(2026, 3, 8), "500.00", "LØN", 1)),
    ]
    assert {
        (e.import_run_id, e.record_ordinal)
        for e in admitted.transaction_evidence
        if e.transaction_id == rema
    } == {("run-a", 2), ("run-b", 2)}
    assert [i.resolved_by for i in admitted.review_items] == ["d-0002"]


def test_each_dropped_transaction_needs_its_own_decision() -> None:
    neither = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("05.03.2026", "BOG", "-25,00", "930,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 9),
    )
    first_coffee = identity(MARCH_3, "-30.00", "KAFFE", 1)

    one_decided = build_from(
        TWO_COFFEES,
        neither,
        decisions=[Withdrawn(decision_id="d-0003", transaction_id=first_coffee)],
    )
    both_decided = build_from(
        TWO_COFFEES,
        neither,
        decisions=[
            Withdrawn(decision_id="d-0003", transaction_id=first_coffee),
            Withdrawn(decision_id="d-0004", transaction_id=SECOND_COFFEE),
        ],
    )

    assert sorted(
        (i.transaction_id, i.resolved_by) for i in one_decided.review_items
    ) == sorted([(first_coffee, "d-0003"), (SECOND_COFFEE, None)])
    assert _statuses(one_decided)["run-b"] == "quarantined"
    assert _statuses(both_decided)["run-b"] == "accepted"
    assert [t.description for t in both_decided.transactions] == ["NETTO", "BOG"]
    assert [t.balance for t in both_decided.transactions] == [
        Decimal("955.00"),
        Decimal("930.00"),
    ]


def test_an_export_under_the_wrong_account_drops_and_disagrees() -> None:
    # Another account's export: different rows, different balances.
    elsewhere = export(
        [
            row("01.03.2026", "HUSLEJE", "-6.000,00", "12.000,00"),
            row("03.03.2026", "EL", "-450,00", "11.550,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 9),
    )

    result = build_from(TWO_COFFEES, elsewhere)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "quarantined"}
    assert {i.kind for i in result.review_items} == {
        "dropped-transactions",
        "export-disagreement",
    }
