# Copyright 2026 Therkel
"""Accounts without bank categories, and an export that loses them (#138).

Opening balance 1000,00 throughout.
"""

from datetime import date

from budget.silver import SilverResult
from tests.silver.exports import build_from, declared, export, row, uncategorised

# Two exports of one account, each balanced against its own rows.
OLDER = [
    row("01.03.2026", "NETTO", "-45,00", "955,00"),
    row("05.03.2026", "BOG", "-25,00", "930,00"),
]
NEWER = [
    row("05.03.2026", "BOG", "-25,00", "930,00"),
    row("08.03.2026", "LØN", "500,00", "1.430,00"),
]


def _statuses(result: SilverResult) -> dict[str, str]:
    return {r.import_run_id: r.status for r in result.import_run_results}


def _errors(result: SilverResult, run_id: str) -> list[tuple[int | None, str]]:
    [run] = [r for r in result.import_run_results if r.import_run_id == run_id]
    return [(e.record_ordinal, e.code) for e in run.errors]


def test_an_export_without_categories_reads_with_null_labels() -> None:
    quiet_labels = export(
        [
            uncategorised(row("01.03.2026", "NETTO", "-45,00", "955,00")),
            uncategorised(row("02.03.2026", "KAFFE", "-30,00", "925,00")),
        ]
    )

    result = build_from(quiet_labels)

    assert _statuses(result) == {"run-0001": "accepted"}
    assert [(t.bank_category, t.bank_subcategory) for t in result.transactions] == [
        (None, None),
        (None, None),
    ]


def test_an_export_that_loses_its_categories_is_held_back() -> None:
    labelled = export(OLDER, run_id="run-a", exported_on=date(2026, 3, 6))
    unlabelled = export(
        [uncategorised(fields) for fields in NEWER],
        run_id="run-b",
        exported_on=date(2026, 3, 9),
    )

    result = build_from(labelled, unlabelled)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "quarantined"}
    assert _errors(result, "run-b") == [(None, "label-layout-regressed")]
    assert result.review_items == ()
    assert [t.description for t in result.transactions] == ["NETTO", "BOG"]


def test_an_older_export_without_categories_lets_a_newer_one_add_them() -> None:
    unlabelled = export(
        [uncategorised(fields) for fields in OLDER],
        run_id="run-a",
        exported_on=date(2026, 3, 6),
    )
    labelled = export(NEWER, run_id="run-b", exported_on=date(2026, 3, 9))

    result = build_from(unlabelled, labelled)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}
    assert [(t.description, t.bank_category) for t in result.transactions] == [
        ("NETTO", None),
        ("BOG", "Mad"),
        ("LØN", "Mad"),
    ]


def test_an_export_without_categories_on_dates_no_labelled_export_covers() -> None:
    labelled = export(OLDER, run_id="run-a", exported_on=date(2026, 3, 6))
    later = declared(
        export(
            [uncategorised(row("08.03.2026", "LØN", "500,00", "1.430,00"))],
            run_id="run-b",
            exported_on=date(2026, 3, 9),
        ),
        covers_from=date(2026, 3, 7),
    )

    result = build_from(labelled, later)

    assert _statuses(result) == {"run-a": "accepted", "run-b": "accepted"}
