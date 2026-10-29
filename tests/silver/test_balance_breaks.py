# Copyright 2026 Therkel
"""Balance breaks and *accept discrepancy* (#92, ADR-010, ADR-016).

Issue #5's scenario 10 for a booked row with a blank balance and for a chain
break within the export.
"""

from datetime import date
from decimal import Decimal

from budget.silver import AcceptDiscrepancy, ReviewItem, SilverResult
from tests.silver.exports import ACCOUNT, build_from, export, review_item_id, row

MARCH_1 = date(2026, 3, 1)
MARCH_2 = date(2026, 3, 2)
MARCH_3 = date(2026, 3, 3)

# The bank states no balance on 2 March's first coffee.
BLANK = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("02.03.2026", "KAFFE", "-30,00", "925,00"),
        row("02.03.2026", "KAFFE", "-30,00", ""),
        row("03.03.2026", "BOG", "-25,00", "870,00"),
    ]
)
# 955,00 - 30,00 is 925,00, but the bank states 900,00 on 2 March.
BROKEN = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("02.03.2026", "KAFFE", "-30,00", "900,00"),
        row("03.03.2026", "BOG", "-25,00", "875,00"),
    ]
)
ACCEPT_BLANK = AcceptDiscrepancy(
    decision_id="d-0001", import_run_id=BLANK.run.import_run_id
)


def _errors(result: SilverResult) -> list[tuple[int | None, str]]:
    [run] = result.import_run_results
    return [(error.record_ordinal, error.code) for error in run.errors]


def test_a_booked_row_without_a_balance_quarantines_the_run() -> None:
    result = build_from(BLANK)

    [run] = result.import_run_results
    assert run.status == "quarantined"
    assert _errors(result) == [(3, "missing-balance")]
    assert result.transactions == ()


def test_a_missing_balance_raises_a_balance_break_review_item() -> None:
    result = build_from(BLANK)

    expected_id = review_item_id("balance-break", BLANK.run.import_run_id)
    assert result.review_items == (
        ReviewItem(
            review_item_id=expected_id,
            kind="balance-break",
            account_id=ACCOUNT,
            date_from=MARCH_2,
            date_to=MARCH_2,
            payload_ids=(BLANK.run.payload_id,),
            resolved_by=None,
        ),
    )
    [run] = result.import_run_results
    assert run.review_item_ids == (expected_id,)


def test_a_chain_break_is_an_error_on_the_later_row_and_re_anchors_the_chain() -> None:
    result = build_from(BROKEN)

    [run] = result.import_run_results
    assert run.status == "quarantined"
    # The 3 March row follows on from the stated 900,00, so it breaks nothing.
    assert _errors(result) == [(2, "balance-chain-break")]
    [item] = result.review_items
    assert (item.kind, item.date_from, item.date_to) == (
        "balance-break",
        MARCH_2,
        MARCH_2,
    )


def test_the_row_after_a_missing_balance_is_not_checked_against_it() -> None:
    unverifiable = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("02.03.2026", "KAFFE", "-30,00", ""),
            row("03.03.2026", "BOG", "-25,00", "700,00"),
        ]
    )

    assert _errors(build_from(unverifiable)) == [(2, "missing-balance")]


def test_replaying_the_same_inputs_raises_the_same_review_item() -> None:
    first = build_from(BLANK).review_items

    assert first
    assert build_from(BLANK).review_items == first


def test_accept_discrepancy_admits_the_run_and_settles_its_review_item() -> None:
    result = build_from(BLANK, decisions=[ACCEPT_BLANK])

    [run] = result.import_run_results
    assert run.status == "accepted"
    assert _errors(result) == [(3, "missing-balance")]
    [item] = result.review_items
    assert item.resolved_by == "d-0001"
    assert run.review_item_ids == (item.review_item_id,)


def test_an_admitted_missing_balance_stays_null() -> None:
    result = build_from(BLANK, decisions=[ACCEPT_BLANK])

    assert [t.balance for t in result.transactions] == [
        Decimal("955.00"),
        Decimal("925.00"),
        None,
        Decimal("870.00"),
    ]
    assert [
        (o.balance_date, o.end_of_day_balance) for o in result.balance_observations
    ] == [(MARCH_1, Decimal("955.00")), (MARCH_2, None), (MARCH_3, Decimal("870.00"))]


def test_accept_discrepancy_admits_a_chain_break_with_the_stated_balances() -> None:
    accept = AcceptDiscrepancy(
        decision_id="d-0002", import_run_id=BROKEN.run.import_run_id
    )

    result = build_from(BROKEN, decisions=[accept])

    [run] = result.import_run_results
    assert run.status == "accepted"
    assert [t.balance for t in result.transactions] == [
        Decimal("955.00"),
        Decimal("900.00"),
        Decimal("875.00"),
    ]


def test_accept_discrepancy_does_not_settle_other_errors() -> None:
    both = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("02.03.2026", "KAFFE", "-30,00", ""),
            row("03.03.2026", "BOG", "-25,0,0", "900,00"),
        ]
    )
    accept = AcceptDiscrepancy(
        decision_id="d-0003", import_run_id=both.run.import_run_id
    )

    result = build_from(both, decisions=[accept])

    [run] = result.import_run_results
    assert run.status == "quarantined"
    assert _errors(result) == [(2, "missing-balance"), (3, "unparseable-decimal")]
    [item] = result.review_items
    assert item.resolved_by == "d-0003"


def test_a_decision_for_another_run_settles_nothing() -> None:
    elsewhere = AcceptDiscrepancy(decision_id="d-0004", import_run_id="run-9999")

    result = build_from(BLANK, decisions=[elsewhere])

    [run] = result.import_run_results
    assert run.status == "quarantined"
    assert [item.resolved_by for item in result.review_items] == [None]
