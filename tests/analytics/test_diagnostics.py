# Copyright 2026 Therkel
"""Kontrol diagnostics from public Gold observations."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.analytics import (
    AccountEvidence,
    MoneyInOut,
    ReportContext,
    TransferSummary,
    diagnostics,
)
from budget.gold import (
    GoldResult,
    GoldTransaction,
    ReportingMonth,
    TransactionType,
)
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS

GOLD = GoldResult(PUBLICATION, RECORDS)


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


def test_transfer_count_counts_selected_legs_and_records_public_pairing() -> None:
    # Only A is selected; T1's public B leg identifies the pair but is not counted.
    report = diagnostics(GOLD, _context(1), is_current=True)

    assert report.transfers == TransferSummary(
        money_in=Decimal("0.00"),
        money_out=Decimal("-3000.00"),
        count=1,
        paired_count=1,
        one_sided_count=0,
    )


def test_no_evidence_keeps_counts_unknown_and_reports_direct_evidence_through() -> None:
    # May's Evidence through does not turn June into evidence.
    context = replace(_context(6), reference_date=date(2026, 6, 3))

    report = diagnostics(GOLD, context, is_current=True)

    assert (
        report.evidence,
        report.unclassified,
        report.adjustments,
        report.transfers,
    ) == (
        (
            AccountEvidence(
                account_id=CURRENT,
                display_name="Joint current",
                evidence_through=date(2026, 5, 8),
            ),
        ),
        None,
        None,
        None,
    )
