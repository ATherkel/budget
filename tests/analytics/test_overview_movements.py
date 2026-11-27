# Copyright 2026 Therkel
"""The rows behind the monthly overview's summary groups (`report-contract.md`).

Expected values come from the Gold worked example's tables and the parent
issue's worked examples, not from the code under test.
"""

from datetime import date

from budget.analytics import MonthlyOverview, ReportContext, monthly_overview
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
