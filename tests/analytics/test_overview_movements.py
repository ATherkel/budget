# Copyright 2026 Therkel
"""The rows behind the monthly overview's summary groups (`report-contract.md`).

Expected values come from the Gold worked example's tables and the parent
issue's worked examples, not from the code under test.
"""

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
from budget.gold import GoldResult, ReportingMonth
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
