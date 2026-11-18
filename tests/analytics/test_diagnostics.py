# Copyright 2026 Therkel
"""Kontrol diagnostics from public Gold observations."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.analytics import (
    MoneyInOut,
    ReportContext,
    diagnostics,
)
from budget.gold import (
    GoldResult,
    GoldTransaction,
    ReportingMonth,
    TransactionType,
)
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS


def _context(month: int, *account_ids: str) -> ReportContext:
    return ReportContext(
        publication_id=1,
        account_ids=frozenset(account_ids or (CURRENT,)),
        month=ReportingMonth(2026, month),
        reference_date=date(2026, 5, 14),
    )


def _transaction(
    transaction_id: str,
    transaction_date: date,
    sequence: int,
    amount: str,
    transaction_type: TransactionType,
) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=transaction_id,
        account_id=CURRENT,
        transaction_date=transaction_date,
        account_sequence=sequence,
        amount=Decimal(amount),
        description="SYNTHETIC",
        transaction_type=transaction_type,
        transfer_group_id=None,
        balance_after=None,
        balance_check="missing_balance",
    )


def test_unknown_and_adjustment_money_stay_separate_and_never_net() -> None:
    # report-contract.md, "Two unknown transactions, +450.00 and -450.00".
    synthetic = replace(
        RECORDS,
        transactions=(
            *RECORDS.transactions,
            _transaction("unknown-in", date(2026, 3, 5), 100, "450.00", "unknown"),
            _transaction("adjustment-in", date(2026, 3, 6), 101, "20.00", "adjustment"),
        ),
        category_allocations=RECORDS.category_allocations,
    )

    report = diagnostics(
        GoldResult(PUBLICATION, synthetic),
        _context(3),
        is_current=True,
    )

    assert (report.unclassified, report.adjustments) == (
        MoneyInOut(Decimal("450.00"), Decimal("-450.00"), 2),
        MoneyInOut(Decimal("20.00"), Decimal("0.00"), 1),
    )
