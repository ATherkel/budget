# Copyright 2026 Therkel
"""Selection options and selection validation of `report-contract.md` (#179).

Every expected value is copied from the contract's worked examples, not
derived from the code under test.
"""

from datetime import date

from budget.analytics import (
    ReportPublication,
    SelectableAccount,
    SelectionOptions,
    selection_options,
)
from budget.gold import GoldRecords, GoldResult, ReportingMonth
from tests.gold.worked_example import PUBLICATION, RECORDS

GOLD = GoldResult(PUBLICATION, RECORDS)
REFERENCE_DATE = date(2026, 5, 14)
P1 = ReportPublication(
    publication_id=1,
    kind="pipeline",
    label=None,
    known_at=PUBLICATION.known_at,
    is_current=True,
)
JOINT_ACCOUNTS = (
    SelectableAccount("joint-current", "Joint current", "current", "household", "DKK"),
    SelectableAccount("joint-savings", "Joint savings", "savings", "household", "DKK"),
)


def test_a_page_may_select_every_account_from_the_first_snapshot_month() -> None:
    assert selection_options(GOLD, REFERENCE_DATE, is_current=True) == (
        SelectionOptions(
            publication=P1,
            accounts=JOINT_ACCOUNTS,
            first_month=ReportingMonth(2026, 1),
            last_month=ReportingMonth(2026, 5),
        )
    )


def test_before_any_snapshot_only_the_reference_month_is_selectable() -> None:
    gold = GoldResult(PUBLICATION, GoldRecords(accounts=RECORDS.accounts))

    options = selection_options(gold, REFERENCE_DATE, is_current=True)

    assert (options.first_month, options.last_month) == (
        ReportingMonth(2026, 5),
        ReportingMonth(2026, 5),
    )
