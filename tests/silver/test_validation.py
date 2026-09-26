# Copyright 2026 Therkel
"""Validation and whole-run quarantine (#91).

Issue #5's scenarios 10 (malformed amount, unknown status) and 12, and the
data map's Date, Decimal and Booking status rules for invalid input.
"""

from dataclasses import replace
from datetime import date

import pytest

from budget.bronze.models import FormatFailure
from budget.silver import SilverResult
from tests.silver.exports import FORMAT, build_from, export, row

VALID = row("01.03.2026", "NETTO", "-45,00", "955,00")


def _errors(result: SilverResult) -> list[tuple[int | None, str]]:
    """Each error of the only run, as (record_ordinal, code)."""
    [run] = result.import_run_results
    return [(error.record_ordinal, error.code) for error in run.errors]


def _assert_contributes_nothing(result: SilverResult) -> None:
    [run] = result.import_run_results
    assert run.status == "quarantined"
    assert result.transactions == ()
    assert result.transaction_evidence == ()
    assert result.unbooked_records == ()
    assert result.balance_observations == ()
    assert result.account_evidence == ()


def test_a_format_failure_quarantines_the_run_with_no_covered_from() -> None:
    empty = export([], covers_through=date(2026, 3, 4))
    failed = replace(
        empty,
        failures=(
            FormatFailure(
                payload_id=empty.run.payload_id,
                source_format=FORMAT,
                reason="unexpected header",
            ),
        ),
    )

    result = build_from(failed)

    _assert_contributes_nothing(result)
    assert _errors(result) == [(None, "format-failure")]
    [run] = result.import_run_results
    assert run.errors[0].payload_id == failed.run.payload_id
    assert run.covered_from is None
    assert run.covered_to == date(2026, 3, 4)


def test_one_bad_record_quarantines_the_whole_run_and_every_error_is_listed() -> None:
    run = export(
        [
            VALID,
            row("02.03.2026", "KAFFE", "-30,0,0", "925,00"),
            row("02.03.2026", "BIO", "-100,00", "825,00", Status="Venter"),
            row("03.03.2026", "BOG", "-25,00", "800,00", Status="Slettet"),
        ]
    )

    result = build_from(run)

    _assert_contributes_nothing(result)
    assert _errors(result) == [(2, "unparseable-decimal"), (3, "unknown-status")]


def test_a_record_lists_each_of_its_errors_in_field_order() -> None:
    result = build_from(export([row("1.3.2026", "NETTO", "-45", "9,5,5")]))

    assert _errors(result) == [
        (1, "unparseable-date"),
        (1, "unparseable-decimal"),
    ]


@pytest.mark.parametrize(
    "dato", ["1.09.2026", " 12.09.2026", "12-09-2026", "31.02.2026", "2026.09.12"]
)
def test_a_date_not_exactly_dd_mm_yyyy_is_unparseable(dato: str) -> None:
    result = build_from(export([row(dato, "NETTO", "-45,00", "955,00")]))

    _assert_contributes_nothing(result)
    assert _errors(result) == [(1, "unparseable-date")]


@pytest.mark.parametrize(
    "belob", ["", "1.23,00", "1234.567,00", "-45,001", " -45,00", "45,", "+45,00"]
)
def test_a_malformed_amount_is_unparseable_and_never_rounded(belob: str) -> None:
    result = build_from(export([row("01.03.2026", "NETTO", belob, "955,00")]))

    _assert_contributes_nothing(result)
    assert _errors(result) == [(1, "unparseable-decimal")]


def test_a_malformed_balance_on_a_booked_row_is_unparseable() -> None:
    result = build_from(export([row("01.03.2026", "NETTO", "-45,00", "955,005")]))

    assert _errors(result) == [(1, "unparseable-decimal")]


@pytest.mark.parametrize("status", [" Udført", "udført", "Venter", ""])
def test_status_matches_exactly(status: str) -> None:
    result = build_from(
        export([row("01.03.2026", "NETTO", "-45,00", "955,00", Status=status)])
    )

    _assert_contributes_nothing(result)
    assert _errors(result) == [(1, "unknown-status")]


def test_a_record_without_exactly_the_format_fields_has_a_wrong_field_count() -> None:
    missing = {name: value for name, value in VALID.items() if name != "Afstemt"}
    extra = VALID | {"Valør": "01.03.2026"}

    result = build_from(export([VALID, missing, extra]))

    _assert_contributes_nothing(result)
    assert _errors(result) == [(2, "wrong-field-count"), (3, "wrong-field-count")]


def test_a_quarantined_run_does_not_count_toward_account_evidence() -> None:
    admitted = export([VALID], run_id="run-0001", covers_through=date(2026, 3, 4))
    quarantined = export(
        [row("09.03.2026", "NETTO", "-45,00", "x")],
        run_id="run-0002",
        exported_on=date(2026, 3, 12),
        covers_through=date(2026, 3, 10),
    )

    result = build_from(admitted, quarantined)

    assert [r.status for r in result.import_run_results] == ["accepted", "quarantined"]
    assert [e.evidence_through for e in result.account_evidence] == [date(2026, 3, 4)]
    assert [t.transaction_date for t in result.transactions] == [date(2026, 3, 1)]
