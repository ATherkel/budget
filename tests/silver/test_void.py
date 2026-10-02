# Copyright 2026 Therkel
"""Voided import runs (#96).

Issue #5's scenario 13, and ADR-009's remedy for two exports produced on the
same day. Opening balance 1000,00 throughout.
"""

from datetime import UTC, date, datetime

from budget.silver import SilverResult, VoidImportRun
from tests.silver.exports import (
    ACCOUNT,
    build_from,
    export,
    presented,
    repeat,
    row,
)

SAVINGS = "joint-savings"

CURRENT = export(
    [
        row("01.03.2026", "NETTO", "-45,00", "955,00"),
        row("03.03.2026", "KAFFE", "-30,00", "925,00"),
    ],
    run_id="run-a",
    exported_on=date(2026, 3, 4),
)
SAVINGS_ROWS = [
    row("01.03.2026", "RENTE", "12,00", "20.012,00"),
    row("03.03.2026", "OVERFØRSEL", "500,00", "20.512,00"),
]


def _statuses(result: SilverResult) -> dict[str, str]:
    return {r.import_run_id: r.status for r in result.import_run_results}


def test_voiding_a_wrong_account_run_lets_its_bytes_count_for_the_right_one() -> None:
    wrong = presented(
        export(SAVINGS_ROWS, run_id="run-wrong", exported_on=date(2026, 3, 5)),
        account_id=ACCOUNT,
        payload_id="payload-savings",
    )
    right = presented(
        export(
            SAVINGS_ROWS,
            run_id="run-right",
            exported_on=date(2026, 3, 5),
            started_at=datetime(2026, 3, 6, tzinfo=UTC),
        ),
        account_id=SAVINGS,
        payload_id="payload-savings",
    )

    unvoided = build_from(CURRENT, wrong)
    result = build_from(
        CURRENT,
        wrong,
        right,
        decisions=[VoidImportRun(decision_id="d-0001", import_run_id="run-wrong")],
    )

    assert _statuses(unvoided)["run-wrong"] == "quarantined"
    assert _statuses(result) == {"run-a": "accepted", "run-right": "accepted"}
    assert result.review_items == ()
    current = [t for t in result.transactions if t.account_id == ACCOUNT]
    assert current == list(build_from(CURRENT).transactions)
    assert [t.description for t in result.transactions if t.account_id == SAVINGS] == [
        "RENTE",
        "OVERFØRSEL",
    ]
    assert "run-wrong" not in {e.import_run_id for e in result.transaction_evidence}
    assert [e.account_id for e in result.account_evidence] == [ACCOUNT, SAVINGS]


def test_voiding_the_newer_same_day_run_admits_the_one_it_quarantined() -> None:
    exported_on = date(2026, 3, 4)
    fuller = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("03.03.2026", "KAFFE", "-30,00", "925,00"),
        ],
        run_id="run-full",
        exported_on=exported_on,
        started_at=datetime(2026, 3, 4, 9, tzinfo=UTC),
    )
    shorter = export(
        [
            row("01.03.2026", "NETTO", "-45,00", "955,00"),
            row("02.03.2026", "BOG", "-25,00", "930,00"),
        ],
        run_id="run-short",
        exported_on=exported_on,
        started_at=datetime(2026, 3, 4, 10, tzinfo=UTC),
    )
    void = VoidImportRun(decision_id="d-0002", import_run_id="run-full")

    assert _statuses(build_from(fuller, shorter))["run-short"] == "quarantined"
    result = build_from(fuller, shorter, decisions=[void])

    assert _statuses(result) == {"run-short": "accepted"}
    assert [t.description for t in result.transactions] == ["NETTO", "BOG"]


def test_a_voided_run_is_no_evidence_and_neither_are_its_repeats() -> None:
    void = VoidImportRun(decision_id="d-0003", import_run_id="run-a")

    again = repeat(CURRENT, run_id="run-a2", exported_on=date(2026, 3, 20))

    result = build_from(CURRENT, again, decisions=[void])

    assert result.import_run_results == ()
    assert result.transactions == ()
    assert result.account_evidence == ()
