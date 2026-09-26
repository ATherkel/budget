# Copyright 2026 Therkel
"""Merging overlapping exports by content and occurrence (#93, ADR-009).

Issue #5's scenarios 2, 3, 4 (across exports), 5, 6, 8, 14, 15 and 16.
Opening balance 1000,00 throughout.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from budget.silver import AccountEvidence, SilverResult, Transaction
from tests.silver.exports import ACCOUNT, build_from, export, identity, repeat, row

MARCH_1 = date(2026, 3, 1)
MARCH_3 = date(2026, 3, 3)
MARCH_5 = date(2026, 3, 5)
MARCH_8 = date(2026, 3, 8)

# Scenario 3's A and B, with scenario 4's two coffees in both.
A = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        row("03.03.2026", "KAFFE", "-30,00", "895,00"),
        row("05.03.2026", "BOG", "-25,00", "870,00"),
    ],
    run_id="run-a",
    exported_on=date(2026, 3, 6),
)
B = export(
    [
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        row("03.03.2026", "KAFFE", "-30,00", "895,00"),
        row("05.03.2026", "BOG", "-25,00", "870,00"),
        row("08.03.2026", "LØN", "500,00", "1.370,00"),
    ],
    run_id="run-b",
    exported_on=date(2026, 3, 9),
)


def _keys(result: SilverResult) -> list[tuple[date, str, int]]:
    return [
        (t.transaction_date, t.description, t.occurrence) for t in result.transactions
    ]


def _by_description(result: SilverResult, description: str) -> Transaction:
    [found] = [t for t in result.transactions if t.description == description]
    return found


def _statuses(result: SilverResult) -> dict[str, str]:
    return {r.import_run_id: r.status for r in result.import_run_results}


def test_overlapping_rows_collapse_to_the_same_transactions() -> None:
    result = build_from(A, B)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}
    assert _keys(result) == [
        (MARCH_1, "NETTO", 1),
        (MARCH_3, "KAFFE", 1),
        (MARCH_3, "KAFFE", 2),
        (MARCH_5, "BOG", 1),
        (MARCH_8, "LØN", 1),
    ]
    alone = build_from(A).transactions
    assert [t.transaction_id for t in result.transactions][:4] == [
        t.transaction_id for t in alone
    ]
    assert result.review_items == ()


def test_each_record_showing_a_transaction_is_its_evidence() -> None:
    result = build_from(A, B)

    first_coffee = identity(MARCH_3, "-30.00", "KAFFE", 1)
    assert sorted(
        (e.import_run_id, e.record_ordinal)
        for e in result.transaction_evidence
        if e.transaction_id == first_coffee
    ) == [("run-a", 2), ("run-b", 1)]


def test_a_repeat_run_adds_nothing_but_extends_evidence() -> None:
    again = repeat(A, run_id="run-a2", exported_on=date(2026, 3, 20))

    result = build_from(A, again)

    assert result.transactions == build_from(A).transactions
    assert [r.import_run_id for r in result.import_run_results] == ["run-a"]
    assert result.account_evidence == (
        AccountEvidence(account_id=ACCOUNT, evidence_through=date(2026, 3, 19)),
    )


def test_a_repeat_of_a_quarantined_payload_is_no_evidence() -> None:
    broken = export([row("01.03.2026", "NETTO", "-45,00", "x")], run_id="run-x")
    again = repeat(broken, run_id="run-x2", exported_on=date(2026, 3, 20))

    assert build_from(broken, again).account_evidence == ()


def test_evidence_through_is_the_maximum_over_admitted_runs() -> None:
    result = build_from(A, B)

    assert result.account_evidence == (
        AccountEvidence(account_id=ACCOUNT, evidence_through=MARCH_8),
    )


def test_a_later_booking_on_the_final_date_is_explained_growth() -> None:
    one_coffee = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        ],
        run_id="run-a",
        exported_on=MARCH_3,
    )

    result = build_from(one_coffee, B)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}
    assert (MARCH_3, "KAFFE", 2) in _keys(result)
    assert result.review_items == ()


def test_a_different_same_day_order_keeps_identifiers_and_takes_the_later_order() -> (
    None
):
    first = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("03.03.2026", "KAFFE", "-30,00", "925,00"),
            row("03.03.2026", "BOG", "-25,00", "900,00"),
        ],
        run_id="run-a",
        exported_on=date(2026, 3, 4),
    )
    reordered = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("03.03.2026", "BOG", "-25,00", "930,00"),
            row("03.03.2026", "KAFFE", "-30,00", "900,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 6),
    )

    result = build_from(first, reordered)

    assert {t.transaction_id for t in result.transactions} == {
        t.transaction_id for t in build_from(first).transactions
    }
    march_3 = [t for t in result.transactions if t.transaction_date == MARCH_3]
    assert [(t.description, t.day_sequence, t.balance) for t in march_3] == [
        ("BOG", 1, Decimal("930.00")),
        ("KAFFE", 2, Decimal("900.00")),
    ]


def test_text_differing_only_in_whitespace_is_one_transaction() -> None:
    first = export(
        [row("01.03.2026", "KAFFE BAR", "-30,00", "970,00")],
        run_id="run-a",
        exported_on=date(2026, 3, 2),
    )
    spaced = export(
        [row("01.03.2026", "KAFFE  BAR ", "-30,00", "970,00")],
        run_id="run-b",
        exported_on=date(2026, 3, 4),
    )

    result = build_from(first, spaced)

    assert _keys(result) == [(MARCH_1, "KAFFE BAR", 1)]
    assert result.transactions == build_from(first).transactions


def test_import_order_does_not_change_the_result() -> None:
    # B imported before A: B's run starts first, but A was exported first.
    b_first = export(
        [dict(r.fields) for r in B.records],
        run_id="run-b",
        exported_on=B.run.exported_on,
        started_at=datetime(2026, 3, 10, 8, tzinfo=UTC),
    )
    a_second = export(
        [dict(r.fields) for r in A.records],
        run_id="run-a",
        exported_on=A.run.exported_on,
        started_at=datetime(2026, 3, 10, 9, tzinfo=UTC),
    )

    result = build_from(b_first, a_second)

    in_order = build_from(A, B)
    assert result.transactions == in_order.transactions
    assert result.transaction_evidence == in_order.transaction_evidence
    assert result.account_evidence == in_order.account_evidence
    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}


def test_rebuilding_from_the_same_inputs_gives_the_same_result() -> None:
    assert build_from(A, B) == build_from(A, B)


def test_a_late_booking_is_admitted_and_later_dates_take_its_balances() -> None:
    before = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("06.03.2026", "KAFFE", "-30,00", "925,00"),
            row("08.03.2026", "BOG", "-25,00", "900,00"),
        ],
        run_id="run-a",
        exported_on=MARCH_8,
    )
    # A purchase dated 7 March, booked 9 March, shifts later balances by -200.
    late = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("06.03.2026", "KAFFE", "-30,00", "925,00"),
            row("07.03.2026", "IKEA", "-200,00", "725,00"),
            row("08.03.2026", "BOG", "-25,00", "700,00"),
            row("10.03.2026", "LØN", "500,00", "1.200,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 12),
    )

    result = build_from(before, late)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}
    existing = {t.transaction_id for t in build_from(before).transactions}
    assert existing <= {t.transaction_id for t in result.transactions}
    assert _by_description(result, "IKEA").balance == Decimal("725.00")
    assert _by_description(result, "BOG").balance == Decimal("700.00")


def test_a_relabelled_transaction_keeps_its_identifier() -> None:
    labelled = export(
        [row("01.03.2026", "NETTO", "-45,00", "955,00", Kategori=" Mad ")],
        run_id="run-a",
        exported_on=date(2026, 3, 2),
    )
    relabelled = export(
        [row("01.03.2026", "NETTO", "-45,00", "955,00", Kategori=" Indkøb ")],
        run_id="run-b",
        exported_on=date(2026, 3, 4),
    )

    [before] = build_from(labelled).transactions
    [after] = build_from(labelled, relabelled).transactions

    assert after.transaction_id == before.transaction_id
    assert after.bank_category == "Indkøb"


def test_a_later_export_hiding_an_admitted_transaction_is_quarantined() -> None:
    hiding = export(
        [
            row("03.03.2026", "KAFFE", "-30,00", "925,00"),
            row("05.03.2026", "BOG", "-25,00", "900,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 9),
    )

    result = build_from(A, hiding)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "quarantined"}
    assert result.transactions == build_from(A).transactions


def test_a_later_export_with_unexplained_balances_is_quarantined() -> None:
    shifted = export(
        [
            row("03.03.2026", "KAFFE", "-30,00", "825,00"),
            row("03.03.2026", "KAFFE", "-30,00", "795,00"),
            row("05.03.2026", "BOG", "-25,00", "770,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 9),
    )

    result = build_from(A, shifted)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "quarantined"}
    assert result.transactions == build_from(A).transactions
    assert result.account_evidence == build_from(A).account_evidence
