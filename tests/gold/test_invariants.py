# Copyright 2026 Therkel
"""The Gold contract invariant check reports each broken invariant by name (#253)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from budget.gold import (
    Coverage,
    GoldAccount,
    GoldRecords,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from tests.gold.invariants import (
    Violation,
    assert_contract_invariants,
    contract_violations,
)
from tests.gold.worked_example import PUBLICATION

ACCOUNT = "synthetic-current"
LAGGING = "synthetic-savings"
DECEMBER = ReportingMonth(2025, 12)
JANUARY = ReportingMonth(2026, 1)
FEBRUARY = ReportingMonth(2026, 2)
MARCH = ReportingMonth(2026, 3)
APRIL = ReportingMonth(2026, 4)


def account(
    evidence_through: date,
    *,
    account_id: str = ACCOUNT,
    closed_on: date | None = None,
) -> GoldAccount:
    """One account whose evidence runs through `evidence_through`."""
    return GoldAccount(
        account_id=account_id,
        display_name=f"Synthetic {account_id}",
        account_type="current",
        ownership_scope="household",
        currency="DKK",
        closed_on=closed_on,
        coverage_start=date(2026, 1, 1),
        evidence_through=evidence_through,
    )


def transaction(
    account_sequence: int,
    transaction_date: date,
    *,
    account_id: str = ACCOUNT,
    amount: str = "1.00",
) -> GoldTransaction:
    """One booked transaction with no stated balance."""
    return GoldTransaction(
        transaction_id=f"{account_id}-{account_sequence:02d}",
        account_id=account_id,
        transaction_date=transaction_date,
        account_sequence=account_sequence,
        amount=Decimal(amount),
        description=f"TEXT {account_sequence}",
        transaction_type="unknown",
        transfer_group_id=None,
        balance_after=None,
        balance_check="missing_balance",
    )


def snapshot(
    month: ReportingMonth,
    coverage: Coverage = "partial",
    opening: str | None = None,
    closing: str | None = None,
    *,
    account_id: str = ACCOUNT,
) -> MonthlyBalanceSnapshot:
    """One row for `month`; `partial` with no balance unless told otherwise."""
    return MonthlyBalanceSnapshot(
        account_id=account_id,
        month=month,
        opening_balance=None if opening is None else Decimal(opening),
        closing_balance=None if closing is None else Decimal(closing),
        coverage=coverage,
        late_bookings_settled=True,
    )


def result_of(
    accounts: Sequence[GoldAccount],
    transactions: Sequence[GoldTransaction],
    balances: Sequence[MonthlyBalanceSnapshot],
) -> GoldResult:
    """A `GoldResult` holding only these records."""
    return GoldResult(
        PUBLICATION,
        GoldRecords(
            accounts=accounts, transactions=transactions, monthly_balances=balances
        ),
    )


def january_only(*transactions: GoldTransaction) -> GoldResult:
    """One account with evidence through January, which has one partial row."""
    return result_of(
        [account(evidence_through=date(2026, 1, 31))],
        transactions,
        [snapshot(JANUARY)],
    )


def january_through_march(*months: ReportingMonth) -> GoldResult:
    """One account booked from January, evidence through March, rows for `months`."""
    return result_of(
        [account(evidence_through=date(2026, 3, 31))],
        [transaction(1, date(2026, 1, 5))],
        [snapshot(month) for month in months],
    )


# Invariant 10: account_sequence and transaction_date.


def test_a_gap_in_account_sequence_breaks_invariant_10() -> None:
    result = january_only(
        transaction(1, date(2026, 1, 5)),
        transaction(2, date(2026, 1, 6)),
        transaction(4, date(2026, 1, 7)),
    )

    assert contract_violations(result) == [
        Violation(10, ACCOUNT, None, "account_sequence skips from 2 to 4")
    ]


def test_a_sequence_not_starting_at_1_breaks_invariant_10() -> None:
    result = january_only(
        transaction(2, date(2026, 1, 5)),
        transaction(3, date(2026, 1, 6)),
    )

    assert contract_violations(result) == [
        Violation(10, ACCOUNT, None, "account_sequence starts at 2, not 1")
    ]


def test_a_repeated_account_sequence_breaks_invariant_10() -> None:
    result = january_only(
        transaction(1, date(2026, 1, 5)),
        transaction(2, date(2026, 1, 6)),
        replace(transaction(2, date(2026, 1, 6)), transaction_id="repeat"),
        transaction(3, date(2026, 1, 7)),
    )

    assert contract_violations(result) == [
        Violation(10, ACCOUNT, None, "account_sequence 2 appears 2 times")
    ]


def test_transactions_read_in_any_order_are_checked_in_sequence_order() -> None:
    result = january_only(
        transaction(3, date(2026, 1, 7)),
        transaction(1, date(2026, 1, 5)),
        transaction(2, date(2026, 1, 6)),
    )

    assert contract_violations(result) == []


def test_a_transaction_date_going_backwards_breaks_invariant_10() -> None:
    result = january_only(
        transaction(1, date(2026, 1, 6)),
        transaction(2, date(2026, 1, 5)),
    )

    assert contract_violations(result) == [
        Violation(
            10,
            ACCOUNT,
            None,
            "transaction_date goes back from 2026-01-06 to 2026-01-05 "
            "at account_sequence 2",
        )
    ]


# Invariant 12: one row per account per month of the managed period.


@pytest.mark.parametrize(
    ("rows", "missing"),
    [
        pytest.param((FEBRUARY, MARCH), JANUARY, id="first"),
        pytest.param((JANUARY, MARCH), FEBRUARY, id="middle"),
        pytest.param((JANUARY, FEBRUARY), MARCH, id="last"),
    ],
)
def test_a_missing_month_breaks_invariant_12(
    rows: tuple[ReportingMonth, ...], missing: ReportingMonth
) -> None:
    result = january_through_march(*rows)

    assert contract_violations(result) == [
        Violation(12, ACCOUNT, missing, "month of the managed period has no row")
    ]


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param(DECEMBER, id="before the first booked transaction"),
        pytest.param(APRIL, id="after the latest published month"),
    ],
)
def test_an_extra_month_breaks_invariant_12(extra: ReportingMonth) -> None:
    result = january_through_march(JANUARY, FEBRUARY, MARCH, extra)

    assert contract_violations(result) == [
        Violation(12, ACCOUNT, extra, "row is outside the managed period")
    ]


def test_the_managed_period_runs_across_a_year_end() -> None:
    result = result_of(
        [account(evidence_through=date(2026, 2, 28))],
        [transaction(1, date(2025, 12, 5))],
        [snapshot(DECEMBER), snapshot(FEBRUARY)],
    )

    assert contract_violations(result) == [
        Violation(12, ACCOUNT, JANUARY, "month of the managed period has no row")
    ]


def test_a_duplicated_month_breaks_invariant_12() -> None:
    result = january_through_march(JANUARY, FEBRUARY, FEBRUARY, MARCH)

    assert contract_violations(result) == [
        Violation(12, ACCOUNT, FEBRUARY, "month has 2 rows")
    ]


def test_the_managed_period_ends_at_the_month_of_an_earlier_closed_on() -> None:
    result = result_of(
        [account(evidence_through=date(2026, 3, 31), closed_on=date(2026, 2, 10))],
        [transaction(1, date(2026, 1, 5))],
        [snapshot(JANUARY), snapshot(FEBRUARY), snapshot(MARCH)],
    )

    assert contract_violations(result) == [
        Violation(12, ACCOUNT, MARCH, "row is outside the managed period")
    ]


def test_a_lagging_account_has_rows_through_the_latest_published_month() -> None:
    result = result_of(
        [
            account(evidence_through=date(2026, 3, 31)),
            account(evidence_through=date(2026, 1, 31), account_id=LAGGING),
        ],
        [
            transaction(1, date(2026, 1, 5)),
            transaction(1, date(2026, 1, 5), account_id=LAGGING),
        ],
        [
            snapshot(JANUARY),
            snapshot(FEBRUARY),
            snapshot(MARCH),
            snapshot(JANUARY, account_id=LAGGING),
        ],
    )

    assert contract_violations(result) == [
        Violation(12, LAGGING, FEBRUARY, "month of the managed period has no row"),
        Violation(12, LAGGING, MARCH, "month of the managed period has no row"),
    ]


def test_an_account_with_no_booked_transaction_has_no_rows() -> None:
    result = result_of(
        [account(evidence_through=date(2026, 1, 31))],
        [],
        [snapshot(JANUARY, "no_data")],
    )

    assert contract_violations(result) == [
        Violation(12, ACCOUNT, JANUARY, "row is outside the managed period")
    ]


# Invariant 12: a complete row's balances add up.


@pytest.mark.parametrize(
    ("opening", "closing", "problem"),
    [
        pytest.param(None, "102.00", "complete row has no opening_balance", id="open"),
        pytest.param("100.00", None, "complete row has no closing_balance", id="close"),
    ],
)
def test_a_complete_row_with_a_null_balance_breaks_invariant_12(
    opening: str | None, closing: str | None, problem: str
) -> None:
    result = result_of(
        [account(evidence_through=date(2026, 1, 31))],
        [transaction(1, date(2026, 1, 5)), transaction(2, date(2026, 1, 6))],
        [snapshot(JANUARY, "complete", opening, closing)],
    )

    assert contract_violations(result) == [Violation(12, ACCOUNT, JANUARY, problem)]


def test_a_complete_row_whose_sum_does_not_add_up_breaks_invariant_12() -> None:
    result = result_of(
        [account(evidence_through=date(2026, 1, 31))],
        [transaction(1, date(2026, 1, 5)), transaction(2, date(2026, 1, 6))],
        [snapshot(JANUARY, "complete", "100.00", "105.00")],
    )

    assert contract_violations(result) == [
        Violation(
            12,
            ACCOUNT,
            JANUARY,
            "opening_balance 100.00 + amounts 2.00 != closing_balance 105.00",
        )
    ]


def test_only_amounts_dated_in_the_month_count_towards_its_sum() -> None:
    result = result_of(
        [account(evidence_through=date(2026, 2, 28))],
        [
            transaction(1, date(2026, 1, 31), amount="50.00"),
            transaction(2, date(2026, 2, 1), amount="2.00"),
        ],
        [
            snapshot(JANUARY, "complete", "0.00", "50.00"),
            snapshot(FEBRUARY, "complete", "50.00", "52.00"),
        ],
    )

    assert contract_violations(result) == []


def test_another_accounts_amounts_never_count_towards_a_rows_sum() -> None:
    result = result_of(
        [
            account(evidence_through=date(2026, 1, 31)),
            account(evidence_through=date(2026, 1, 31), account_id=LAGGING),
        ],
        [
            transaction(1, date(2026, 1, 5), amount="2.00"),
            transaction(1, date(2026, 1, 5), account_id=LAGGING, amount="50.00"),
        ],
        [
            snapshot(JANUARY, "complete", "100.00", "102.00"),
            snapshot(JANUARY, "complete", "0.00", "50.00", account_id=LAGGING),
        ],
    )

    assert contract_violations(result) == []


@pytest.mark.parametrize("coverage", ["partial", "no_data"])
@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        pytest.param(None, None, id="null balances"),
        pytest.param("100.00", "105.00", id="sum does not add up"),
    ],
)
def test_a_row_that_is_not_complete_is_never_checked_for_balances(
    coverage: Coverage, opening: str | None, closing: str | None
) -> None:
    result = result_of(
        [account(evidence_through=date(2026, 1, 31))],
        [transaction(1, date(2026, 1, 5)), transaction(2, date(2026, 1, 6))],
        [snapshot(JANUARY, coverage, opening, closing)],
    )

    assert contract_violations(result) == []


# Reporting: every violation, in one failure.


def test_a_result_keeping_both_invariants_passes() -> None:
    result = result_of(
        [account(evidence_through=date(2026, 2, 28))],
        [transaction(1, date(2026, 1, 5)), transaction(2, date(2026, 2, 6))],
        [
            snapshot(JANUARY, "complete", "100.00", "101.00"),
            snapshot(FEBRUARY, "complete", "101.00", "102.00"),
        ],
    )

    assert_contract_invariants(result)


def test_every_violation_is_reported_in_one_failure() -> None:
    result = result_of(
        [account(evidence_through=date(2026, 3, 31))],
        [transaction(1, date(2026, 1, 5)), transaction(3, date(2026, 1, 6))],
        [
            snapshot(JANUARY, "complete", "100.00", "105.00"),
            snapshot(MARCH),
        ],
    )

    with pytest.raises(AssertionError) as failure:
        assert_contract_invariants(result)

    message = str(failure.value)
    assert "account_sequence skips from 1 to 3" in message
    assert "month of the managed period has no row" in message
    assert "!= closing_balance 105.00" in message
