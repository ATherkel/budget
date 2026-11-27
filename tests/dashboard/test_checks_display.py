# Copyright 2026 Therkel
"""Kontrol's lines, built from diagnostics without a dashboard.

Covers the cases the worked example cannot publish; `test_checks.py` drives
the rest through the dashboard.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.analytics import (
    AccountMonthCoverage,
    ReportContext,
    ReportCoverage,
    diagnostics,
)
from budget.dashboard.features.checks.display import checks_view
from budget.gold import GoldResult, ReportingMonth
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

MARCH = ReportingMonth(2026, 3)
MARCH_REPORT = diagnostics(
    GoldResult(PUBLICATION, RECORDS),
    ReportContext(
        publication_id=1,
        account_ids=frozenset({CURRENT, SAVINGS}),
        month=MARCH,
        reference_date=date(2026, 5, 14),
    ),
    is_current=True,
)


def test_a_month_outside_an_accounts_history_is_not_listed_as_incomplete() -> None:
    coverage = ReportCoverage(
        "partial",
        (
            AccountMonthCoverage(CURRENT, "Joint current", MARCH, "no_data"),
            AccountMonthCoverage(SAVINGS, "Joint savings", MARCH, "outside_history"),
        ),
    )
    outside_only = ReportCoverage(
        "no_data",
        (AccountMonthCoverage(SAVINGS, "Joint savings", MARCH, "outside_history"),),
    )

    assert (
        checks_view(replace(MARCH_REPORT, coverage=coverage), "marts 2026").incomplete,
        checks_view(
            replace(MARCH_REPORT, coverage=outside_only), "marts 2026"
        ).incomplete,
    ) == (
        ["Joint current, marts 2026: ingen data."],
        ["Ingen valgte kontomåneder mangler dækning."],
    )


def test_a_positive_residual_shows_its_plus_sign_in_the_account_table() -> None:
    # The worked example cannot publish a nonzero internal residual.
    reconciliations = tuple(
        replace(reconciliation, internal_residual=Decimal("12.40"))
        if reconciliation.account_id == SAVINGS
        else reconciliation
        for reconciliation in MARCH_REPORT.reconciliations
    )
    view = checks_view(
        replace(MARCH_REPORT, reconciliations=reconciliations), "marts 2026"
    )
    row = {account.account_id: account for account in view.accounts}[SAVINGS]

    assert (row.internal, row.waterfall[-1].amount) == ("+12,40 kr.", "+12,40 kr.")


def savings_verdict(**changes: Decimal | None) -> str:
    """Return Joint savings' March verdict with its reconciliation `changes`."""
    reconciliations = tuple(
        replace(reconciliation, **changes)
        if reconciliation.account_id == SAVINGS
        else reconciliation
        for reconciliation in MARCH_REPORT.reconciliations
    )
    view = checks_view(
        replace(MARCH_REPORT, reconciliations=reconciliations), "marts 2026"
    )
    return {account.account_id: account.verdict for account in view.accounts}[SAVINGS]


def test_a_complete_month_with_a_nonzero_residual_does_not_add_up() -> None:
    # Joint savings is fully covered in March, so only the arithmetic speaks.
    assert (
        savings_verdict(internal_residual=Decimal("12.40")),
        savings_verdict(opening_gap=Decimal("-3.00")),
    ) == ("Går ikke op (+12,40 kr.)", "Går ikke op (\N{MINUS SIGN}3,00 kr.)")


def test_a_complete_month_with_a_missing_balance_is_unknown() -> None:
    # Without both balances the arithmetic cannot be checked either way.
    assert (
        savings_verdict(closing_balance=None, internal_residual=None),
        savings_verdict(opening_balance=None, internal_residual=None, opening_gap=None),
    ) == ("Ukendt", "Ukendt")


def test_a_complete_month_with_an_unknown_residual_is_unknown() -> None:
    # A first imported month has no previous close; unknown arithmetic proves nothing.
    assert (
        savings_verdict(opening_gap=None),
        savings_verdict(internal_residual=None),
        savings_verdict(internal_residual=None, opening_gap=Decimal("-3.00")),
    ) == ("Ukendt", "Ukendt", "Ukendt")


def test_a_month_outside_an_accounts_history_says_so_rather_than_finding_nothing() -> (
    None
):
    reconciliations = tuple(
        replace(reconciliation, coverage="outside_history")
        if reconciliation.account_id == SAVINGS
        else reconciliation
        for reconciliation in MARCH_REPORT.reconciliations
    )
    view = checks_view(
        replace(MARCH_REPORT, reconciliations=reconciliations), "marts 2026"
    )

    assert {account.account_id: account.verdict for account in view.accounts}[
        SAVINGS
    ] == "Uden for historikken"


def test_with_both_residuals_nonzero_the_internal_one_names_the_gap() -> None:
    # The month's own arithmetic comes before its link to the previous close.
    assert (
        savings_verdict(
            internal_residual=Decimal("12.40"), opening_gap=Decimal("-3.00")
        )
        == "Går ikke op (+12,40 kr.)"
    )


def test_a_missing_step_after_a_known_start_leaves_later_totals_unknown() -> None:
    reconciliations = tuple(
        replace(reconciliation, income_minus_expenses=None, internal_residual=None)
        if reconciliation.account_id == SAVINGS
        else reconciliation
        for reconciliation in MARCH_REPORT.reconciliations
    )
    view = checks_view(
        replace(MARCH_REPORT, reconciliations=reconciliations), "marts 2026"
    )
    waterfall = {account.account_id: account for account in view.accounts}[
        SAVINGS
    ].waterfall

    assert [(step.label, step.amount, step.total) for step in waterfall[1:8]] == [
        ("Indtægter minus udgifter", "Ukendt", "Ukendt"),
        ("Overførsler", "0,00 kr.", "Ukendt"),
        ("Ukategoriseret ind", "0,00 kr.", "Ukendt"),
        ("Ukategoriseret ud", "0,00 kr.", "Ukendt"),
        ("Regulering ind", "0,00 kr.", "Ukendt"),
        ("Regulering ud", "0,00 kr.", "Ukendt"),
        ("Beregnet slutsaldo", "", "Ukendt"),
    ]


def test_the_waterfall_sets_the_computed_and_the_banks_close_in_one_column() -> None:
    # The two closes the reader compares sit one under the other; the start
    # balance is printed once, as the first running total.
    waterfall = {
        account.account_id: account
        for account in checks_view(MARCH_REPORT, "marts 2026").accounts
    }[CURRENT].waterfall

    assert [
        (step.label, step.amount, step.total)
        for step in (waterfall[0], *waterfall[-3:])
    ] == [
        ("Startsaldo", "", "37.037,50 kr."),
        ("Beregnet slutsaldo", "", "35.587,50 kr."),
        ("Bankens slutsaldo", "", "35.587,50 kr."),
        ("Forskel", "0,00 kr.", ""),
    ]
