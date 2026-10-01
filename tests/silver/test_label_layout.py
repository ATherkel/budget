# Copyright 2026 Therkel
"""Accounts without bank categories, and an export that loses them (#138).

Opening balance 1000,00 throughout.
"""

from budget.silver import SilverResult
from tests.silver.exports import build_from, export, row, uncategorised


def _statuses(result: SilverResult) -> dict[str, str]:
    return {r.import_run_id: r.status for r in result.import_run_results}


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
