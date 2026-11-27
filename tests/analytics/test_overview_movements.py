# Copyright 2026 Therkel
"""The rows behind the monthly overview's summary groups (`report-contract.md`).

Expected values come from the Gold worked example's tables and the parent
issue's worked examples, not from the code under test.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.analytics import (
    MoneyInOut,
    MonthlyOverview,
    MovementGroup,
    MovementRow,
    ReportContext,
    SummaryGroup,
    monthly_overview,
)
from budget.gold import (
    GoldCategoryAllocation,
    GoldResult,
    GoldTransaction,
    ReportingMonth,
    TransactionType,
)
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

GOLD = GoldResult(PUBLICATION, RECORDS)


def _overview(
    month: int, *account_ids: str, gold: GoldResult = GOLD
) -> MonthlyOverview:
    context = ReportContext(
        publication_id=1,
        account_ids=frozenset(account_ids or (CURRENT, SAVINGS)),
        month=ReportingMonth(2026, month),
        reference_date=date(2026, 5, 14),
    )
    return monthly_overview(gold, context, is_current=True)


def test_the_summary_groups_come_in_card_order() -> None:
    movements = _overview(2).movements or ()

    assert [group.group for group in movements] == [
        "income",
        "expenses",
        "transfers",
        "unclassified",
    ]


def _group(overview: MonthlyOverview, name: SummaryGroup) -> MovementGroup:
    return next(group for group in overview.movements or () if group.group == name)


def test_an_income_row_carries_its_bank_amount_and_contribution() -> None:
    # February's salary, current-07 in the worked example.
    assert _group(_overview(2), "income") == MovementGroup(
        group="income",
        rows=(
            MovementRow(
                transaction_date=date(2026, 2, 25),
                description="SALARY",
                account_id=CURRENT,
                account_display_name="Joint current",
                amount=Decimal("25000.00"),
                contribution=Decimal("25000.00"),
            ),
        ),
        total=Decimal("25000.00"),
        flows=MoneyInOut(Decimal("25000.00"), Decimal("0.00"), 1),
    )


def _contributions(group: MovementGroup) -> set[tuple[str, Decimal, Decimal]]:
    return {(row.description, row.amount, row.contribution) for row in group.rows}


def test_expenses_count_money_out_as_positive_and_a_refund_reduces_them() -> None:
    # February: rent and groceries, less the groceries Refund; Expenses 9020.00.
    expenses = _group(_overview(2), "expenses")

    assert _contributions(expenses) == {
        ("RENT", Decimal("-8500.00"), Decimal("8500.00")),
        ("GROCERIES", Decimal("-640.00"), Decimal("640.00")),
        ("GROCERIES", Decimal("120.00"), Decimal("-120.00")),
    }
    assert expenses.total == Decimal("9020.00")


def _booked(
    seq: int, amount: str, transaction_type: TransactionType, category_id: str | None
) -> tuple[GoldTransaction, tuple[GoldCategoryAllocation, ...]]:
    """One synthetic March booking on joint-current, after the example's rows."""
    transaction = GoldTransaction(
        transaction_id=f"march-{seq:02d}",
        account_id=CURRENT,
        transaction_date=date(2026, 3, 10),
        account_sequence=100 + seq,
        amount=Decimal(amount),
        description=f"MARCH {seq}",
        transaction_type=transaction_type,
        transfer_group_id=None,
        balance_after=None,
        balance_check="consistent",
    )
    allocations = (
        ()
        if category_id is None
        else (
            GoldCategoryAllocation(
                allocation_id=f"march-{seq:02d}/{category_id}",
                transaction_id=transaction.transaction_id,
                account_id=CURRENT,
                transaction_date=transaction.transaction_date,
                category_id=category_id,
                amount=transaction.amount,
            ),
        )
    )
    return transaction, allocations


def _with(
    *bookings: tuple[GoldTransaction, tuple[GoldCategoryAllocation, ...]],
) -> GoldResult:
    return GoldResult(
        PUBLICATION,
        replace(
            RECORDS,
            transactions=(*RECORDS.transactions, *(t for t, _ in bookings)),
            category_allocations=(
                *RECORDS.category_allocations,
                *(a for _, allocations in bookings for a in allocations),
            ),
        ),
    )


def test_an_income_refund_reduces_income() -> None:
    # #628: income of +30.000, +10.000 and a -5.000 salary Refund is 35.000.
    gold = _with(
        _booked(1, "30000.00", "income", "salary"),
        _booked(2, "10000.00", "income", "interest"),
        _booked(3, "-5000.00", "refund", "salary"),
    )

    income = _group(_overview(3, gold=gold), "income")

    assert _contributions(income) == {
        ("MARCH 1", Decimal("30000.00"), Decimal("30000.00")),
        ("MARCH 2", Decimal("10000.00"), Decimal("10000.00")),
        ("MARCH 3", Decimal("-5000.00"), Decimal("-5000.00")),
    }
    assert income.total == Decimal("35000.00")


def test_a_selected_transfer_leg_contributes_its_amount_and_both_legs_cancel() -> None:
    # January's transfer T1: current-02 out, savings-01 in.
    one_leg = _group(_overview(1, CURRENT), "transfers")
    both_legs = _group(_overview(1), "transfers")

    assert _contributions(one_leg) == {
        ("TRANSFER", Decimal("-3000.00"), Decimal("-3000.00")),
    }
    assert one_leg.total == Decimal("-3000.00")
    assert both_legs.total == Decimal("0.00")
    assert both_legs.flows == MoneyInOut(Decimal("3000.00"), Decimal("-3000.00"), 2)


def test_unclassified_money_in_and_out_never_net_to_nothing() -> None:
    # March's unknown -450.00 (current-08) beside a synthetic unknown +450.00.
    gold = _with(_booked(1, "450.00", "unknown", None))

    unclassified = _group(_overview(3, gold=gold), "unclassified")

    assert _contributions(unclassified) == {
        ("UNKNOWN", Decimal("-450.00"), Decimal("-450.00")),
        ("MARCH 1", Decimal("450.00"), Decimal("450.00")),
    }
    assert unclassified.flows == MoneyInOut(Decimal("450.00"), Decimal("-450.00"), 2)
