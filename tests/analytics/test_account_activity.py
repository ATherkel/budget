# Copyright 2026 Therkel
"""Account activity reports from public Gold records."""

from datetime import date
from decimal import Decimal

from budget.analytics import (
    AccountActivitySnapshot,
    ActivityRow,
    BankBalanceObservation,
    MonthlyBalanceObservation,
    ReportContext,
    ReportCoverage,
    ReportPublication,
    account_activity,
)
from budget.gold import GoldResult, ReportingMonth
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS

GOLD = GoldResult(PUBLICATION, RECORDS)
P1 = ReportPublication(
    publication_id=1,
    kind="pipeline",
    label=None,
    known_at=PUBLICATION.known_at,
    is_current=True,
)


def _context(month: int, *account_ids: str) -> ReportContext:
    return ReportContext(
        publication_id=1,
        account_ids=frozenset(account_ids or (CURRENT,)),
        month=ReportingMonth(2026, month),
        reference_date=date(2026, 5, 14),
    )


def test_dated_observation_and_monthly_snapshot_remain_separate_values() -> None:
    # report-contract.md, "April's last transaction is on 24 April".
    context = _context(4)
    report = account_activity(GOLD, context, is_current=True)

    assert (
        report.context,
        report.publication,
        report.currency,
        report.accounts,
        report.coverage,
        report.provisional,
    ) == (
        context,
        P1,
        "DKK",
        (
            AccountActivitySnapshot(
                account_id=CURRENT,
                display_name="Joint current",
                dated_balance=BankBalanceObservation(
                    transaction_date=date(2026, 4, 24),
                    balance_after=Decimal("52087.50"),
                ),
                earlier_observation=BankBalanceObservation(
                    transaction_date=date(2026, 3, 20),
                    balance_after=Decimal("35587.50"),
                ),
                monthly_snapshot=MonthlyBalanceObservation(
                    opening_balance=Decimal("35587.50"),
                    closing_balance=Decimal("52087.50"),
                    coverage="complete",
                    late_bookings_settled=True,
                ),
                evidence_through=date(2026, 5, 8),
                coverage="complete",
            ),
        ),
        ReportCoverage(status="complete", account_months=()),
        None,
    )


def test_selected_transfer_names_its_public_pair_without_adding_the_other_leg() -> None:
    # A is selected and B is outside it; both public legs share transfer group T1.
    report = account_activity(GOLD, _context(1, CURRENT), is_current=True)
    transfers = tuple(
        row for row in report.transactions if row.transaction_type == "transfer"
    )

    assert transfers == (
        ActivityRow(
            transaction_date=date(2026, 1, 20),
            description="TRANSFER",
            account_id=CURRENT,
            account_display_name="Joint current",
            amount=Decimal("-3000.00"),
            transaction_type="transfer",
            transfer_pairing="paired",
            counterpart_account_id="joint-savings",
            counterpart_account_display_name="Joint savings",
            counterpart_transaction_date=date(2026, 1, 20),
        ),
    )
