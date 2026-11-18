# Copyright 2026 Therkel
"""Account activity reports from public Gold records."""

from datetime import date
from decimal import Decimal

from budget.analytics import (
    AccountActivity,
    AccountActivitySnapshot,
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

    assert account_activity(GOLD, context, is_current=True) == AccountActivity(
        context=context,
        publication=P1,
        currency="DKK",
        accounts=(
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
        coverage=ReportCoverage(status="complete", account_months=()),
        provisional=None,
    )
