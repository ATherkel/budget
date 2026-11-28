# Copyright 2026 Therkel
"""Account activity reports from public Gold records."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest.mock import ANY

import pytest

from budget.analytics import (
    AccountActivitySnapshot,
    ActivityRow,
    BankBalanceObservation,
    InvalidSelectionError,
    MoneyInOut,
    MonthlyBalanceObservation,
    ReportContext,
    ReportCoverage,
    ReportPublication,
    RowClassification,
    account_activity,
    monthly_overview,
)
from budget.gold import (
    Classification,
    GoldResult,
    GoldTransaction,
    ReportingMonth,
    TransactionType,
)
from tests.analytics.test_monthly_overview import LATER_GOLD, NEW, PERSON
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

GOLD = GoldResult(PUBLICATION, RECORDS)
P1 = ReportPublication(
    publication_id=1,
    kind="pipeline",
    label=None,
    known_at=PUBLICATION.known_at,
    is_current=True,
)


def _context(
    month: int,
    *account_ids: str,
    publication_id: int = 1,
) -> ReportContext:
    return ReportContext(
        publication_id=publication_id,
        account_ids=frozenset(account_ids or (CURRENT,)),
        month=ReportingMonth(2026, month),
        reference_date=date(2026, 5, 14),
    )


def test_an_activity_row_names_what_classified_it_and_its_category_and_group() -> None:
    # February's groceries at NETTO, current-05, decided by the rule r-netto.
    by_rule = Classification("rule", rule_ids=("r-netto",))
    gold = GoldResult(
        PUBLICATION,
        replace(
            RECORDS,
            transactions=tuple(
                replace(t, classification=by_rule)
                if t.transaction_id == "current-05"
                else t
                for t in RECORDS.transactions
            ),
        ),
    )

    report = account_activity(gold, _context(2), is_current=True)

    [netto] = [row for row in report.transactions if row.amount == Decimal("-640.00")]
    assert netto.classification == RowClassification(by_rule, "Groceries", "Food")


def test_dated_observation_and_monthly_snapshot_remain_separate_values() -> None:
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
                # The money_in_out tests below pin it.
                money_in_out=ANY,
            ),
        ),
        ReportCoverage(status="complete", account_months=()),
        None,
    )


def test_a_quiet_partial_month_keeps_unknown_snapshot_balances() -> None:
    report = account_activity(GOLD, _context(5), is_current=True)
    [account] = report.accounts

    assert (
        account.dated_balance,
        account.earlier_observation,
        account.monthly_snapshot,
        account.coverage,
        report.transactions,
    ) == (
        None,
        BankBalanceObservation(
            transaction_date=date(2026, 4, 24),
            balance_after=Decimal("52087.50"),
        ),
        MonthlyBalanceObservation(
            opening_balance=None,
            closing_balance=None,
            coverage="partial",
            late_bookings_settled=False,
        ),
        "partial",
        (),
    )


def test_a_quiet_complete_month_keeps_the_earlier_observation_dated() -> None:
    report = account_activity(GOLD, _context(2, SAVINGS), is_current=True)
    [account] = report.accounts

    assert (
        account.dated_balance,
        account.earlier_observation,
        account.monthly_snapshot,
        account.coverage,
        report.transactions,
    ) == (
        None,
        BankBalanceObservation(
            transaction_date=date(2026, 1, 20),
            balance_after=Decimal("53000.00"),
        ),
        MonthlyBalanceObservation(
            opening_balance=Decimal("53000.00"),
            closing_balance=Decimal("53000.00"),
            coverage="complete",
            late_bookings_settled=True,
        ),
        "complete",
        (),
    )


def test_the_latest_null_balance_is_not_replaced_by_an_earlier_known_one() -> None:
    january = next(
        transaction
        for transaction in RECORDS.transactions
        if transaction.transaction_id == "current-03"
    )
    earlier = next(
        transaction
        for transaction in RECORDS.transactions
        if transaction.transaction_id == "current-04"
    )
    latest = replace(
        earlier,
        transaction_id="current-null",
        transaction_date=date(2026, 2, 3),
        account_sequence=12,
        balance_after=None,
        balance_check="missing_balance",
    )
    february = ReportingMonth(2026, 2)
    snapshots = tuple(
        replace(snapshot, closing_balance=None)
        if snapshot.account_id == CURRENT and snapshot.month == february
        else snapshot
        for snapshot in RECORDS.monthly_balances
    )
    gold = GoldResult(
        PUBLICATION,
        replace(
            RECORDS,
            transactions=(january, earlier, latest),
            monthly_balances=snapshots,
        ),
    )

    report = account_activity(gold, _context(2), is_current=True)
    [account] = report.accounts

    assert (
        account.dated_balance,
        account.earlier_observation,
        account.monthly_snapshot,
    ) == (
        BankBalanceObservation(
            transaction_date=date(2026, 2, 3),
            balance_after=None,
        ),
        BankBalanceObservation(
            transaction_date=date(2026, 1, 28),
            balance_after=Decimal("21557.50"),
        ),
        MonthlyBalanceObservation(
            opening_balance=Decimal("21557.50"),
            closing_balance=None,
            coverage="partial",
            late_bookings_settled=True,
        ),
    )


def test_evidence_through_keeps_a_genuine_null() -> None:
    no_evidence = replace(
        RECORDS.accounts[0],
        coverage_start=None,
        evidence_through=None,
    )
    gold = GoldResult(
        PUBLICATION,
        replace(
            RECORDS,
            accounts=(no_evidence,),
            transactions=(),
            category_allocations=(),
            monthly_balances=(),
        ),
    )

    report = account_activity(gold, _context(5), is_current=True)

    assert (
        report.accounts[0].evidence_through,
        report.accounts[0].coverage,
        report.accounts[0].monthly_snapshot,
        report.transactions,
    ) == (None, "no_data", None, ())


def test_selected_transfer_names_its_public_pair_without_adding_the_other_leg() -> None:
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


def test_same_month_transfer_keeps_both_selected_signed_legs() -> None:
    report = account_activity(
        GOLD,
        _context(1, CURRENT, SAVINGS),
        is_current=True,
    )

    assert {
        (row.account_id, row.amount, row.transfer_pairing)
        for row in report.transactions
        if row.transaction_type == "transfer"
    } == {
        (CURRENT, Decimal("-3000.00"), "paired"),
        (SAVINGS, Decimal("3000.00"), "paired"),
    }


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


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (
            1,
            (
                CURRENT,
                date(2026, 1, 31),
                Decimal("-300.00"),
                SAVINGS,
                date(2026, 2, 1),
            ),
        ),
        (
            2,
            (
                SAVINGS,
                date(2026, 2, 1),
                Decimal("300.00"),
                CURRENT,
                date(2026, 1, 31),
            ),
        ),
    ],
    ids=["january", "february"],
)
def test_cross_month_transfer_legs_keep_their_date_and_public_pair(
    month: int,
    expected: tuple[str, date, Decimal, str, date],
) -> None:
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

    report = account_activity(
        gold,
        _context(month, CURRENT, SAVINGS),
        is_current=True,
    )

    assert [
        (
            row.account_id,
            row.transaction_date,
            row.amount,
            row.counterpart_account_id,
            row.counterpart_transaction_date,
        )
        for row in report.transactions
    ] == [expected]


def test_null_group_is_one_sided_and_unknown_description_stays_unknown() -> None:
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
        by_type["unknown"].description,
        by_type["unknown"].transfer_pairing,
    ) == ("one_sided", None, None, "TRANSFER SUGGESTION", None)


def test_publication_mismatch_is_refused_like_the_overview() -> None:
    mismatched = _context(2, publication_id=999)

    with pytest.raises(ValueError, match="context names publication 999") as (
        overview_failure
    ):
        monthly_overview(GOLD, mismatched, is_current=True)
    with pytest.raises(ValueError, match="context names publication 999") as (
        activity_failure
    ):
        account_activity(GOLD, mismatched, is_current=True)

    assert str(activity_failure.value) == str(overview_failure.value)


def test_invalid_selection_is_not_turned_into_a_balance_report() -> None:
    context = replace(_context(2), account_ids=frozenset())

    with pytest.raises(InvalidSelectionError) as raised:
        account_activity(GOLD, context, is_current=True)

    assert raised.value.reasons == {"no_accounts"}


def test_missing_snapshot_status_is_not_coerced_to_complete() -> None:
    february = ReportingMonth(2026, 2)
    unbalanced = tuple(
        snapshot
        for snapshot in RECORDS.monthly_balances
        if not (snapshot.account_id == SAVINGS and snapshot.month == february)
    )
    gold = GoldResult(
        PUBLICATION,
        replace(RECORDS, monthly_balances=unbalanced),
    )

    report = account_activity(gold, _context(2, SAVINGS), is_current=True)

    assert report.accounts[0].coverage == "no_data"


def _booked(
    seq: int, amount: str, transaction_type: TransactionType
) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=f"current-{seq:02d}",
        account_id=CURRENT,
        transaction_date=date(2026, 2, 27),
        account_sequence=seq,
        amount=Decimal(amount),
        description=transaction_type.upper(),
        transaction_type=transaction_type,
        transfer_group_id=None,
        balance_after=None,
        balance_check="consistent",
    )


def test_money_in_and_out_count_every_transaction_type_by_its_sign() -> None:
    # February's current rows: -8,500.00 rent, -640.00 groceries, +120.00 refund
    # and +25,000.00 salary, plus a transfer in, an adjustment out and a zero.
    extra = (
        _booked(20, "300.00", "transfer"),
        _booked(21, "-7.50", "adjustment"),
        _booked(22, "0.00", "unknown"),
    )
    gold = GoldResult(
        PUBLICATION,
        replace(RECORDS, transactions=(*RECORDS.transactions, *extra)),
    )

    [account] = account_activity(gold, _context(2), is_current=True).accounts

    assert account.money_in_out == MoneyInOut(
        money_in=Decimal("25420.00"), money_out=Decimal("-9147.50"), count=7
    )


@pytest.mark.parametrize(
    ("month", "account_id", "expected"),
    [
        # report-contract.md: new-current was never imported, so no evidence.
        (3, NEW, None),
        # "A later account: outside_history": a known, quiet zero.
        (2, PERSON, MoneyInOut(Decimal("0.00"), Decimal("0.00"), 0)),
    ],
)
def test_money_in_and_out_are_unknown_exactly_when_the_account_has_no_data(
    month: int, account_id: str, expected: MoneyInOut | None
) -> None:
    report = account_activity(
        LATER_GOLD, _context(month, SAVINGS, account_id), is_current=True
    )

    [account] = (a for a in report.accounts if a.account_id == account_id)
    assert account.money_in_out == expected
