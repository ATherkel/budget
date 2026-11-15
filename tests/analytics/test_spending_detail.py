# Copyright 2026 Therkel
"""Spending detail over a real test-profile Gold store.

Expected values come from the Spending detail table of the report contract's
worked example, not from the code.
"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budget.analytics import (
    DetailSubject,
    HouseholdReports,
    ReportContext,
)
from budget.gold import GoldResult, ReportingMonth
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import test_profile as make_test_profile
from tests.gold.test_store import CONFIGURATION, RECIPE
from tests.gold.worked_example import PUBLICATION, RECORDS

BOTH = frozenset({"joint-current", "joint-savings"})


@pytest.fixture
def reports(tmp_path: Path) -> Iterator[HouseholdReports]:
    """Read the worked example through the production adapter."""
    profile = make_test_profile(tmp_path)
    migrate_gold(profile)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
        yield HouseholdReports(store)


def _context(month: int, reference_date: date = date(2026, 5, 14)) -> ReportContext:
    return ReportContext(
        publication_id=1,
        account_ids=BOTH,
        month=ReportingMonth(2026, month),
        reference_date=reference_date,
    )


def _category(category_id: str) -> DetailSubject:
    return DetailSubject("category", category_id)


def test_february_groceries_lists_the_purchase_and_its_refund(
    reports: HouseholdReports,
) -> None:
    detail = reports.spending_detail(_context(2), _category("groceries"), "month")

    assert [row.spending for row in detail.rows] == [
        Decimal("-120.00"),
        Decimal("640.00"),
    ]
    assert detail.spending == Decimal("520.00")
