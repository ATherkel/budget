# Copyright 2026 Therkel
"""Kontrol's lines, built from diagnostics without a dashboard.

Covers the cases the worked example cannot publish; `test_checks.py` drives
the rest through the dashboard.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from budget.analytics import (
    AccountMonthCoverage,
    MoneyInOut,
    ReportContext,
    ReportCoverage,
    TransferSummary,
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


def test_a_nonzero_internal_residual_is_listed_first_beside_opening_gaps() -> None:
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

    assert [
        (
            residual.element_id,
            residual.line,
            parse_qs(urlsplit(residual.url).query).get("account"),
        )
        for residual in view.nonzero_residuals
    ] == [
        (
            f"checks-residual-{CURRENT}-opening-gap",
            "Joint current: Åbningsforskel \N{MINUS SIGN}500,00 kr. (se Detaljer)",
            [CURRENT],
        ),
        (
            f"checks-residual-{SAVINGS}-internal",
            "Joint savings: Intern forskel +12,40 kr. (se Detaljer)",
            [SAVINGS],
        ),
    ]


def test_a_positive_residual_shows_its_plus_sign_in_the_accounts_list() -> None:
    # A difference reads with its direction: +12,40 kr., not 12,40 kr.
    reconciliations = tuple(
        replace(reconciliation, internal_residual=Decimal("12.40"))
        if reconciliation.account_id == SAVINGS
        else reconciliation
        for reconciliation in MARCH_REPORT.reconciliations
    )
    view = checks_view(
        replace(MARCH_REPORT, reconciliations=reconciliations), "marts 2026"
    )

    assert {account.account_id: account.residuals for account in view.reconciliations}[
        SAVINGS
    ] == [
        "Intern forskel: +12,40 kr.",
        "Slutsaldo forrige måned: 53.000,00 kr.",
        "Åbningsforskel: 0,00 kr.",
    ]


def test_unknown_observed_groups_keep_both_amounts_and_count_unknown() -> None:
    view = checks_view(
        replace(MARCH_REPORT, unclassified=None, adjustments=None, transfers=None),
        "marts 2026",
    )

    assert [
        (group.money_in, group.money_out, group.count) for group in view.observed
    ] == [
        ("Ukendt", "Ukendt", "Ukendt"),
        ("Ukendt", "Ukendt", "Ukendt"),
        ("Ukendt", "Ukendt", "Ukendt"),
    ]


def test_opposite_observed_amounts_stay_signed_and_never_cancel() -> None:
    view = checks_view(
        replace(
            MARCH_REPORT,
            unclassified=MoneyInOut(Decimal("12.40"), Decimal("-12.40"), 2),
            adjustments=MoneyInOut(Decimal("23.50"), Decimal("-23.50"), 4),
            transfers=TransferSummary(Decimal("34.60"), Decimal("-34.60"), 6, 6, 0),
        ),
        "marts 2026",
    )

    assert [
        (group.money_in, group.money_out, group.count) for group in view.observed
    ] == [
        ("+12,40 kr.", "\N{MINUS SIGN}12,40 kr.", "2"),
        ("+23,50 kr.", "\N{MINUS SIGN}23,50 kr.", "4"),
        ("+34,60 kr.", "\N{MINUS SIGN}34,60 kr.", "6"),
    ]
