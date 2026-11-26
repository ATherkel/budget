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
