# Copyright 2026 Therkel
"""Kontrol diagnostics from public Gold observations."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from budget.analytics import (
    AccountEvidence,
    AccountMonthCoverage,
    InvalidSelectionError,
    MoneyInOut,
    Reconciliation,
    ReportContext,
    TransferSummary,
    diagnostics,
)
from budget.gold import (
    Coverage,
    GoldCategoryAllocation,
    GoldRecords,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
    TransactionType,
)
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

GOLD = GoldResult(PUBLICATION, RECORDS)
REFERENCE_DATE = date(2026, 5, 14)
ZERO = Decimal("0.00")


def _context(
    month: int,
    *account_ids: str,
    publication_id: int = 1,
    reference_date: date = REFERENCE_DATE,
) -> ReportContext:
    return ReportContext(
        publication_id=publication_id,
        account_ids=frozenset(account_ids or (CURRENT,)),
        month=ReportingMonth(2026, month),
        reference_date=reference_date,
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


def _snapshot(
    month: int,
    *,
    account_id: str = CURRENT,
    opening: str | None,
    closing: str | None,
    coverage: Coverage = "partial",
) -> MonthlyBalanceSnapshot:
    return MonthlyBalanceSnapshot(
        account_id=account_id,
        month=ReportingMonth(2026, month),
        opening_balance=None if opening is None else Decimal(opening),
        closing_balance=None if closing is None else Decimal(closing),
        coverage=coverage,
        late_bookings_settled=month <= 4,
    )


def _replace_snapshot(
    records: GoldRecords,
    snapshot: MonthlyBalanceSnapshot,
) -> GoldRecords:
    monthly_balances = tuple(
        row
        for row in records.monthly_balances
        if (row.account_id, row.month) != (snapshot.account_id, snapshot.month)
    )
    return replace(
        records,
        monthly_balances=(*monthly_balances, snapshot),
    )


def test_unknown_and_adjustment_money_stay_separate_and_never_net() -> None:
    synthetic = replace(
        RECORDS,
        transactions=(
            *RECORDS.transactions,
            _transaction(
                "unknown-in",
                date(2026, 3, 5),
                100,
                "450.00",
                "unknown",
            ),
            _transaction(
                "adjustment-in",
                date(2026, 3, 6),
                101,
                "20.00",
                "adjustment",
            ),
        ),
    )

    report = diagnostics(
        GoldResult(PUBLICATION, synthetic),
        _context(3),
        is_current=True,
    )

    assert (report.unclassified, report.adjustments) == (
        MoneyInOut(Decimal("450.00"), Decimal("-450.00"), 2),
        MoneyInOut(Decimal("20.00"), ZERO, 1),
    )


def test_transfer_summary_counts_selected_legs_rather_than_public_pairs() -> None:
    one_account = diagnostics(GOLD, _context(1, CURRENT), is_current=True)
    both_accounts = diagnostics(
        GOLD,
        _context(1, CURRENT, SAVINGS),
        is_current=True,
    )

    assert (one_account.transfers, both_accounts.transfers) == (
        TransferSummary(ZERO, Decimal("-3000.00"), 1, 1, 0),
        TransferSummary(
            Decimal("3000.00"),
            Decimal("-3000.00"),
            2,
            2,
            0,
        ),
    )


def test_a_cross_month_pair_counts_the_selected_month_leg() -> None:
    cross_month = (
        replace(
            _transaction(
                "out-january",
                date(2026, 1, 20),
                1,
                "-100.00",
                "transfer",
            ),
            transfer_group_id="cross-month",
        ),
        replace(
            _transaction(
                "in-february",
                date(2026, 2, 2),
                1,
                "100.00",
                "transfer",
            ),
            account_id=SAVINGS,
            transfer_group_id="cross-month",
        ),
    )
    synthetic = replace(
        RECORDS,
        transactions=cross_month,
        category_allocations=(),
        monthly_balances=(
            _snapshot(1, opening="0.00", closing="-100.00", coverage="complete"),
            _snapshot(
                2,
                opening="-100.00",
                closing="-100.00",
                coverage="complete",
            ),
            _snapshot(
                1,
                account_id=SAVINGS,
                opening="100.00",
                closing="100.00",
                coverage="complete",
            ),
            _snapshot(
                2,
                account_id=SAVINGS,
                opening="0.00",
                closing="100.00",
                coverage="complete",
            ),
        ),
    )

    report = diagnostics(
        GoldResult(PUBLICATION, synthetic),
        _context(2, CURRENT, SAVINGS),
        is_current=True,
    )

    assert report.transfers == TransferSummary(
        money_in=Decimal("100.00"),
        money_out=ZERO,
        count=1,
        paired_count=1,
        one_sided_count=0,
    )


def test_a_one_sided_transfer_stays_selected_and_one_sided() -> None:
    synthetic = replace(
        RECORDS,
        transactions=(
            *RECORDS.transactions,
            _transaction(
                "manual-one-sided",
                date(2026, 2, 28),
                100,
                "-25.00",
                "transfer",
            ),
        ),
    )

    report = diagnostics(
        GoldResult(PUBLICATION, synthetic),
        _context(2, CURRENT),
        is_current=True,
    )

    assert report.transfers == TransferSummary(
        money_in=ZERO,
        money_out=Decimal("-25.00"),
        count=1,
        paired_count=0,
        one_sided_count=1,
    )


def test_no_data_makes_money_and_counts_unknown_even_when_rows_exist() -> None:
    transactions = (
        _transaction(
            "june-unknown",
            date(2026, 6, 1),
            1,
            "10.00",
            "unknown",
        ),
        _transaction(
            "june-adjustment",
            date(2026, 6, 2),
            2,
            "-20.00",
            "adjustment",
        ),
        _transaction(
            "june-transfer",
            date(2026, 6, 3),
            3,
            "-30.00",
            "transfer",
        ),
    )
    report = diagnostics(
        GoldResult(
            PUBLICATION,
            replace(RECORDS, transactions=(*RECORDS.transactions, *transactions)),
        ),
        _context(6, reference_date=date(2026, 6, 3)),
        is_current=True,
    )

    assert (report.unclassified, report.adjustments, report.transfers) == (
        None,
        None,
        None,
    )
    assert report.evidence == (
        AccountEvidence(CURRENT, "Joint current", date(2026, 5, 8)),
    )


def test_partial_coverage_keeps_observed_counts_and_stays_partial() -> None:
    report = diagnostics(GOLD, _context(3), is_current=True)
    reconciliation = report.reconciliations[0]

    assert report.unclassified == MoneyInOut(ZERO, Decimal("-450.00"), 1)
    assert report.adjustments == MoneyInOut(ZERO, ZERO, 0)
    assert report.transfers == TransferSummary(ZERO, ZERO, 0, 0, 0)
    assert report.coverage.status == "partial"
    assert report.coverage.account_months == (
        AccountMonthCoverage(
            CURRENT,
            "Joint current",
            ReportingMonth(2026, 3),
            "partial",
        ),
    )
    assert report.provisional is None
    assert reconciliation.coverage == "partial"
    assert report.evidence == (
        AccountEvidence(CURRENT, "Joint current", date(2026, 5, 8)),
    )


def test_complete_coverage_and_unknown_money_are_judged_independently() -> None:
    transactions = (
        _transaction(
            "unknown",
            date(2026, 3, 2),
            1,
            "-450.00",
            "unknown",
        ),
        _transaction(
            "adjustment",
            date(2026, 3, 3),
            2,
            "20.00",
            "adjustment",
        ),
    )
    synthetic = replace(
        RECORDS,
        transactions=transactions,
        category_allocations=(),
        monthly_balances=(
            _snapshot(
                3,
                opening="1000.00",
                closing="570.00",
                coverage="complete",
            ),
        ),
    )

    report = diagnostics(
        GoldResult(PUBLICATION, synthetic),
        _context(3),
        is_current=True,
    )

    assert report.coverage.status == "complete"
    assert report.unclassified == MoneyInOut(ZERO, Decimal("-450.00"), 1)
    assert report.adjustments == MoneyInOut(Decimal("20.00"), ZERO, 1)


def test_complete_coverage_can_still_be_provisional() -> None:
    report = diagnostics(
        GOLD,
        _context(3, SAVINGS, reference_date=date(2026, 3, 14)),
        is_current=True,
    )

    assert report.coverage.status == "complete"
    assert report.provisional is not None
    assert report.provisional.reasons == {"current_month"}
    assert report.unclassified == MoneyInOut(ZERO, ZERO, 0)


def test_evidence_through_is_exposed_directly_as_null() -> None:
    accounts = (
        replace(RECORDS.accounts[0], evidence_through=None),
        RECORDS.accounts[1],
    )

    report = diagnostics(
        GoldResult(PUBLICATION, replace(RECORDS, accounts=accounts)),
        _context(3),
        is_current=True,
    )

    assert report.evidence == (AccountEvidence(CURRENT, "Joint current", None),)


def test_reconciliation_keeps_components_and_reports_zero_and_opening_gap() -> None:
    report = diagnostics(GOLD, _context(3), is_current=True)

    assert report.reconciliations == (
        Reconciliation(
            account_id=CURRENT,
            display_name="Joint current",
            month=ReportingMonth(2026, 3),
            opening_balance=Decimal("37037.50"),
            income_minus_expenses=Decimal("-1000.00"),
            transfers=ZERO,
            unclassified_in=ZERO,
            unclassified_out=Decimal("-450.00"),
            adjustments_in=ZERO,
            adjustments_out=ZERO,
            expected_closing=Decimal("35587.50"),
            closing_balance=Decimal("35587.50"),
            internal_residual=ZERO,
            previous_closing_balance=Decimal("37537.50"),
            opening_gap=Decimal("-500.00"),
            coverage="partial",
        ),
    )


def test_complete_reconciliation_keeps_every_approved_component() -> None:
    transactions = (
        _transaction("income", date(2026, 3, 2), 1, "1500.00", "income"),
        _transaction("expense", date(2026, 3, 3), 2, "-1000.00", "expense"),
        _transaction("transfer", date(2026, 3, 4), 3, "-300.00", "transfer"),
        _transaction("unknown-in", date(2026, 3, 5), 4, "450.00", "unknown"),
        _transaction("unknown-out", date(2026, 3, 6), 5, "-450.00", "unknown"),
        _transaction("adjustment", date(2026, 3, 7), 6, "20.00", "adjustment"),
    )
    allocations = (
        GoldCategoryAllocation(
            "income/salary",
            "income",
            CURRENT,
            date(2026, 3, 2),
            "salary",
            Decimal("1500.00"),
        ),
        GoldCategoryAllocation(
            "expense/rent",
            "expense",
            CURRENT,
            date(2026, 3, 3),
            "rent",
            Decimal("-1000.00"),
        ),
    )
    synthetic = replace(
        RECORDS,
        transactions=transactions,
        category_allocations=allocations,
        monthly_balances=(
            _snapshot(
                3,
                opening="1000.00",
                closing="1220.00",
                coverage="complete",
            ),
        ),
    )

    report = diagnostics(
        GoldResult(PUBLICATION, synthetic),
        _context(3),
        is_current=True,
    )

    assert report.coverage.status == "complete"
    assert report.coverage.account_months == ()
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
            adjustments_out=ZERO,
            expected_closing=Decimal("1220.00"),
            closing_balance=Decimal("1220.00"),
            internal_residual=ZERO,
            previous_closing_balance=None,
            opening_gap=None,
            coverage="complete",
        ),
    )


@pytest.mark.parametrize(
    ("opening", "closing", "expected_closing", "internal_residual", "opening_gap"),
    [
        ("37037.50", None, Decimal("35587.50"), None, Decimal("-500.00")),
        (None, "35587.50", None, None, None),
        (None, None, None, None, None),
    ],
)
def test_each_missing_balance_endpoint_makes_its_residual_or_gap_unknown(
    opening: str | None,
    closing: str | None,
    expected_closing: Decimal | None,
    internal_residual: Decimal | None,
    opening_gap: Decimal | None,
) -> None:
    records = _replace_snapshot(
        RECORDS,
        _snapshot(3, opening=opening, closing=closing),
    )

    reconciliation = diagnostics(
        GoldResult(PUBLICATION, records),
        _context(3),
        is_current=True,
    ).reconciliations[0]

    assert (
        reconciliation.expected_closing,
        reconciliation.internal_residual,
        reconciliation.opening_gap,
    ) == (expected_closing, internal_residual, opening_gap)
    assert (
        reconciliation.income_minus_expenses,
        reconciliation.transfers,
        reconciliation.unclassified_in,
        reconciliation.unclassified_out,
        reconciliation.adjustments_in,
        reconciliation.adjustments_out,
    ) == (
        Decimal("-1000.00"),
        ZERO,
        ZERO,
        Decimal("-450.00"),
        ZERO,
        ZERO,
    )


def test_a_missing_previous_endpoint_makes_only_the_opening_gap_unknown() -> None:
    records = _replace_snapshot(
        RECORDS,
        _snapshot(
            1,
            opening="400.00",
            closing="21557.50",
            coverage="complete",
        ),
    )

    reconciliation = diagnostics(
        GoldResult(PUBLICATION, records),
        _context(1),
        is_current=True,
    ).reconciliations[0]

    assert (
        reconciliation.internal_residual,
        reconciliation.previous_closing_balance,
        reconciliation.opening_gap,
    ) == (ZERO, None, None)


def test_a_no_data_reconciliation_keeps_components_unknown() -> None:
    report = diagnostics(
        GOLD,
        _context(6, reference_date=date(2026, 6, 3)),
        is_current=True,
    )

    assert report.reconciliations == (
        Reconciliation(
            account_id=CURRENT,
            display_name="Joint current",
            month=ReportingMonth(2026, 6),
            opening_balance=None,
            income_minus_expenses=None,
            transfers=None,
            unclassified_in=None,
            unclassified_out=None,
            adjustments_in=None,
            adjustments_out=None,
            expected_closing=None,
            closing_balance=None,
            internal_residual=None,
            previous_closing_balance=None,
            opening_gap=None,
            coverage="no_data",
        ),
    )


def test_a_context_naming_another_publication_matches_overview_failure() -> None:
    with pytest.raises(
        ValueError,
        match=("context names publication 999, but publication 1 is open"),
    ):
        diagnostics(
            GOLD,
            _context(3, publication_id=999),
            is_current=True,
        )


def test_invalid_selection_remains_its_own_failure() -> None:
    context = replace(_context(3), account_ids=frozenset())

    with pytest.raises(InvalidSelectionError) as raised:
        diagnostics(GOLD, context, is_current=True)

    assert raised.value.reasons == {"no_accounts"}
