# Copyright 2026 Therkel
"""Kontrol diagnostics from public Gold observations."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.analytics import (
    AccountEvidence,
    MoneyInOut,
    Reconciliation,
    ReportContext,
    TransferSummary,
    diagnostics,
)
from budget.gold import (
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
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


def test_reconciliation_keeps_each_component_and_computes_the_internal_residual() -> (
    None
):
    # report-contract.md, "For a complete synthetic month".
    transactions = (
        _transaction("income", date(2026, 3, 2), 1, "1500.00", "income"),
        _transaction("expense", date(2026, 3, 3), 2, "-1000.00", "expense"),
        _transaction("transfer", date(2026, 3, 4), 3, "-300.00", "transfer"),
        _transaction("unknown-in", date(2026, 3, 5), 4, "450.00", "unknown"),
        _transaction("unknown-out", date(2026, 3, 6), 5, "-450.00", "unknown"),
        _transaction("adjustment", date(2026, 3, 7), 6, "20.00", "adjustment"),
    )
    synthetic = replace(
        RECORDS,
        transactions=transactions,
        category_allocations=(),
        monthly_balances=(
            MonthlyBalanceSnapshot(
                account_id=CURRENT,
                month=ReportingMonth(2026, 3),
                opening_balance=Decimal("1000.00"),
                closing_balance=Decimal("1220.00"),
                coverage="complete",
                late_bookings_settled=True,
            ),
        ),
    )
    report = diagnostics(
        GoldResult(PUBLICATION, synthetic),
        _context(3),
        is_current=True,
    )

    assert report.reconciliations == (
        Reconciliation(
            account_id=CURRENT,
            display_name="Joint current",
            month=ReportingMonth(2026, 3),
            opening_balance=Decimal("1000.00"),
            income_minus_expenses=Decimal("500.00"),
            transfers=Decimal("-300.00"),
            unclassified_in=Decimal("450.00"),
            unclassified_out=Decimal("-450.00"),
            adjustments_in=Decimal("20.00"),
            adjustments_out=Decimal("0.00"),
            closing_balance=Decimal("1220.00"),
            internal_residual=Decimal("0.00"),
            previous_closing_balance=None,
            opening_gap=None,
            coverage="complete",
        ),
    )


def test_reconciliation_reports_the_opening_gap_without_upgrading_coverage() -> None:
    # report-contract.md: March residual zero, February closing 37,537.50.
    report = diagnostics(GOLD, _context(3), is_current=True)
    reconciliation = report.reconciliations[0]

    assert (
        reconciliation.internal_residual,
        reconciliation.previous_closing_balance,
        reconciliation.opening_gap,
        reconciliation.coverage,
    ) == (
        Decimal("0.00"),
        Decimal("37537.50"),
        Decimal("-500.00"),
        "partial",
    )


def test_a_missing_snapshot_endpoint_makes_the_residual_unknown() -> None:
    # May has a snapshot row whose opening and closing balances are unknown.
    report = diagnostics(GOLD, _context(5), is_current=True)
    reconciliation = report.reconciliations[0]

    assert (
        reconciliation.opening_balance,
        reconciliation.closing_balance,
        reconciliation.internal_residual,
        reconciliation.opening_gap,
    ) == (None, None, None, None)
