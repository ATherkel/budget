# Copyright 2026 Therkel
"""Unexplained balance differences between exports (#94, ADR-009).

Opening balance 1000,00 throughout.
"""

from datetime import UTC, date, datetime

from budget.silver import ReviewItem, SilverResult
from tests.silver.exports import ACCOUNT, build_from, export, review_item_id, row

MARCH_3 = date(2026, 3, 3)
MARCH_5 = date(2026, 3, 5)

A = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        row("05.03.2026", "BOG", "-25,00", "900,00"),
    ],
    run_id="run-a",
    exported_on=date(2026, 3, 6),
)
# Shows every admitted transaction, but its balances are 100,00 lower from
# 3 March on, which nothing it adds explains.
SHIFTED = export(
    [
        row("03.03.2026", "KAFFE", "-30,00", "825,00"),
        row("05.03.2026", "BOG", "-25,00", "800,00"),
        row("08.03.2026", "LØN", "500,00", "1.300,00"),
    ],
    run_id="run-b",
    exported_on=date(2026, 3, 9),
)


def _statuses(result: SilverResult) -> dict[str, str]:
    return {r.import_run_id: r.status for r in result.import_run_results}


def test_unexplained_balances_raise_an_export_disagreement() -> None:
    result = build_from(A, SHIFTED)

    expected_id = review_item_id("export-disagreement", "run-b")
    assert result.review_items == (
        ReviewItem(
            review_item_id=expected_id,
            kind="export-disagreement",
            account_id=ACCOUNT,
            date_from=MARCH_3,
            date_to=MARCH_5,
            payload_ids=(SHIFTED.run.payload_id, A.run.payload_id),
            resolved_by=None,
        ),
    )
    [b] = [r for r in result.import_run_results if r.import_run_id == "run-b"]
    assert b.status == "quarantined"
    assert b.errors == ()
    assert b.review_item_ids == (expected_id,)


def test_a_disagreeing_export_leaves_the_admitted_state_alone() -> None:
    result = build_from(A, SHIFTED)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "quarantined"}
    assert result.transactions == build_from(A).transactions
    assert "LØN" not in {t.description for t in result.transactions}
    assert result.account_evidence == build_from(A).account_evidence
    assert {o.payload_id for o in result.balance_observations} == {A.run.payload_id}


def test_a_wholly_new_date_is_counted_at_the_next_date_both_state() -> None:
    # 4 March is new in the later export; its -50,00 shows up in 5 March.
    later = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("03.03.2026", "KAFFE", "-30,00", "925,00"),
            row("04.03.2026", "IKEA", "-50,00", "875,00"),
            row("05.03.2026", "BOG", "-25,00", "850,00"),
        ],
        run_id="run-b",
        exported_on=date(2026, 3, 9),
    )

    result = build_from(A, later)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}
    assert result.review_items == ()


def test_exports_sharing_an_export_date_are_admitted_in_import_order() -> None:
    # Produced the same day; the bank booked KAFFE between the two.
    fuller = [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
    ]
    shorter = [row("01.03.2026", "NETTO", "-45,00", "955,00")]
    exported_on = date(2026, 3, 4)

    def imported(*, full_first: bool) -> SilverResult:
        full_hour, short_hour = (9, 10) if full_first else (10, 9)
        return build_from(
            export(
                fuller,
                run_id="run-full",
                exported_on=exported_on,
                started_at=datetime(2026, 3, 4, full_hour, tzinfo=UTC),
            ),
            export(
                shorter,
                run_id="run-short",
                exported_on=exported_on,
                started_at=datetime(2026, 3, 4, short_hour, tzinfo=UTC),
            ),
        )

    assert _statuses(imported(full_first=True)) == {
        "run-full": "accepted",
        "run-short": "quarantined",
    }
    assert _statuses(imported(full_first=False)) == {
        "run-full": "accepted",
        "run-short": "accepted",
    }
