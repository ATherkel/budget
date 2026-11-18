# Copyright 2026 Therkel
"""Account activity reports from public Gold records."""

from dataclasses import replace
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
from budget.gold import GoldResult, GoldTransaction, ReportingMonth
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

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


def _transfer(
    transaction_id: str,
    account_id: str,
    transaction_date: date,
    amount: str,
    group: str | None,
) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=transaction_id,
        account_id=account_id,
        transaction_date=transaction_date,
        account_sequence=1,
        amount=Decimal(amount),
        description="TRANSFER",
        transaction_type="transfer",
        transfer_group_id=group,
        balance_after=None,
        balance_check="missing_balance",
    )


def test_cross_month_transfer_legs_keep_their_date_and_public_pair() -> None:
    gold = GoldResult(
        PUBLICATION,
        replace(
            RECORDS,
            transactions=(
                _transfer("out", CURRENT, date(2026, 1, 31), "-300.00", "T2"),
                _transfer("in", SAVINGS, date(2026, 2, 1), "300.00", "T2"),
            ),
        ),
    )

    report = account_activity(gold, _context(1, CURRENT), is_current=True)

    assert report.transactions == (
        ActivityRow(
            transaction_date=date(2026, 1, 31),
            description="TRANSFER",
            account_id=CURRENT,
            account_display_name="Joint current",
            amount=Decimal("-300.00"),
            transaction_type="transfer",
            transfer_pairing="paired",
            counterpart_account_id=SAVINGS,
            counterpart_account_display_name="Joint savings",
            counterpart_transaction_date=date(2026, 2, 1),
        ),
    )


def test_null_group_is_one_sided_and_unknown_text_stays_unknown() -> None:
    unknown = GoldTransaction(
        transaction_id="unknown",
        account_id=CURRENT,
        transaction_date=date(2026, 2, 2),
        account_sequence=2,
        amount=Decimal("-50.00"),
        description="TRANSFER SUGGESTION",
        transaction_type="unknown",
        transfer_group_id=None,
        balance_after=None,
        balance_check="missing_balance",
    )
    gold = GoldResult(
        PUBLICATION,
        replace(
            RECORDS,
            transactions=(
                _transfer("one-sided", CURRENT, date(2026, 2, 1), "-300.00", None),
                unknown,
            ),
        ),
    )

    report = account_activity(gold, _context(2, CURRENT), is_current=True)
    by_type = {row.transaction_type: row for row in report.transactions}
    transfer = by_type["transfer"]

    assert (
        transfer.transfer_pairing,
        transfer.counterpart_account_id,
        transfer.counterpart_account_display_name,
        by_type["unknown"].transaction_type,
        by_type["unknown"].transfer_pairing,
    ) == ("one_sided", None, None, "unknown", None)
