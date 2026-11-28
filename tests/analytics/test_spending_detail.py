# Copyright 2026 Therkel
"""Spending detail over a real test-profile Gold store.

Expected values come from the Spending detail table of the report contract's
worked example, not from the code.
"""

from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from budget.analytics import (
    DetailSubject,
    HouseholdReports,
    InvalidSelectionError,
    ReportContext,
    RowClassification,
    SpendingDetail,
    SpendingDetailRow,
)
from budget.gold import (
    Classification,
    GoldCategoryAllocation,
    GoldResult,
    GoldTransaction,
    ReportingMonth,
)
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


def test_a_row_names_its_date_text_account_and_category_but_no_identifiers(
    reports: HouseholdReports,
) -> None:
    detail = reports.spending_detail(_context(2), _category("groceries"), "month")

    assert detail.rows[0] == SpendingDetailRow(
        transaction_date=date(2026, 2, 12),
        description="GROCERIES",
        account_id="joint-current",
        account_display_name="Joint current",
        category_id="groceries",
        category_name="Groceries",
        spending=Decimal("-120.00"),
    )


def test_a_detail_row_names_what_classified_it_and_its_category_and_group(
    tmp_path: Path,
) -> None:
    # February's grocery refund, current-06, decided by the rule r-netto.
    by_rule = Classification("rule", rule_ids=("r-netto",))
    records = replace(
        RECORDS,
        transactions=tuple(
            replace(t, classification=by_rule)
            if t.transaction_id == "current-06"
            else t
            for t in RECORDS.transactions
        ),
    )
    profile = make_test_profile(tmp_path)
    migrate_gold(profile)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, records), RECIPE, CONFIGURATION)
        detail = HouseholdReports(store).spending_detail(
            _context(2), _category("groceries"), "month"
        )

    [refund] = [row for row in detail.rows if row.spending == Decimal("-120.00")]
    assert refund.classification == RowClassification(by_rule, "Groceries", "Food")


def _grocery(
    account_id: str, seq: int, amount: str, booked: date = date(2026, 2, 12)
) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=f"extra-{account_id}-{seq}",
        account_id=account_id,
        transaction_date=booked,
        account_sequence=seq,
        amount=Decimal(amount),
        description="GROCERIES",
        transaction_type="expense",
        transfer_group_id=None,
        balance_after=None,
        balance_check="consistent",
    )


def _groceries_with(
    tmp_path: Path, extra: tuple[GoldTransaction, ...]
) -> SpendingDetail:
    """Return February's groceries detail with `extra` purchases added."""
    records = replace(
        RECORDS,
        transactions=(*RECORDS.transactions, *extra),
        category_allocations=(
            *RECORDS.category_allocations,
            *(
                GoldCategoryAllocation(
                    allocation_id=f"{t.transaction_id}/groceries",
                    transaction_id=t.transaction_id,
                    account_id=t.account_id,
                    transaction_date=t.transaction_date,
                    category_id="groceries",
                    amount=t.amount,
                )
                for t in extra
            ),
        ),
    )
    profile = make_test_profile(tmp_path)
    migrate_gold(profile)
    with GoldStore(profile) as store:
        store.publish(GoldResult(PUBLICATION, records), RECIPE, CONFIGURATION)
        return HouseholdReports(store).spending_detail(
            _context(2), _category("groceries"), "month"
        )


def test_same_day_rows_run_by_account_then_booking_sequence_descending(
    tmp_path: Path,
) -> None:
    detail = _groceries_with(
        tmp_path,
        (
            _grocery("joint-current", 12, "-11.00"),
            _grocery("joint-savings", 3, "-22.00"),
        ),
    )

    assert [(row.account_id, row.spending) for row in detail.rows] == [
        ("joint-savings", Decimal("22.00")),
        ("joint-current", Decimal("11.00")),
        ("joint-current", Decimal("-120.00")),
        ("joint-current", Decimal("640.00")),
    ]


def test_an_older_row_comes_last_whatever_its_account(tmp_path: Path) -> None:
    # 2026-02-01 on Joint savings is older than both February groceries rows on
    # Joint current, so newest-first puts it last despite its account.
    detail = _groceries_with(
        tmp_path, (_grocery("joint-savings", 3, "-22.00", date(2026, 2, 1)),)
    )

    assert [(row.account_id, row.spending) for row in detail.rows] == [
        ("joint-current", Decimal("-120.00")),
        ("joint-current", Decimal("640.00")),
        ("joint-savings", Decimal("22.00")),
    ]


def test_april_housing_year_to_date_lists_every_housing_allocation(
    reports: HouseholdReports,
) -> None:
    detail = reports.spending_detail(
        _context(4), DetailSubject("group", "housing"), "year_to_date"
    )

    assert [(row.description, row.spending) for row in detail.rows] == [
        ("RENT", Decimal("8500.00")),
        ("UTILITIES", Decimal("1000.00")),
        ("RENT", Decimal("8500.00")),
    ]
    assert detail.spending == Decimal("18000.00")
    assert (
        detail.name,
        detail.group_id,
        detail.group_name,
        detail.first_month,
        detail.last_month,
    ) == (
        "Housing",
        "housing",
        "Housing",
        ReportingMonth(2026, 1),
        ReportingMonth(2026, 4),
    )


def test_february_groceries_year_to_date_adds_the_januarys_purchase(
    reports: HouseholdReports,
) -> None:
    detail = reports.spending_detail(
        _context(2), _category("groceries"), "year_to_date"
    )

    assert [row.spending for row in detail.rows] == [
        Decimal("-120.00"),
        Decimal("640.00"),
        Decimal("842.50"),
    ]
    assert detail.spending == Decimal("1362.50")


def test_coverage_names_every_incomplete_account_month_in_the_scope(
    reports: HouseholdReports,
) -> None:
    detail = reports.spending_detail(
        _context(2), _category("groceries"), "year_to_date"
    )

    assert detail.coverage.status == "partial"
    assert [
        (c.account_id, c.month, c.status) for c in detail.coverage.account_months
    ] == [
        ("joint-current", ReportingMonth(2026, 1), "partial"),
        ("joint-current", ReportingMonth(2026, 2), "partial"),
        ("joint-savings", ReportingMonth(2026, 1), "partial"),
    ]
    assert detail.provisional is None


def test_may_year_to_date_is_provisional_for_both_reasons(
    reports: HouseholdReports,
) -> None:
    detail = reports.spending_detail(
        _context(5), _category("groceries"), "year_to_date"
    )

    assert detail.provisional is not None
    assert detail.provisional.reasons == {"current_month", "late_bookings_unsettled"}
    assert [(m.account_id, m.month) for m in detail.provisional.unsettled] == [
        ("joint-current", ReportingMonth(2026, 5)),
        ("joint-savings", ReportingMonth(2026, 5)),
    ]
    assert detail.spending == Decimal("1362.50")


def test_a_month_without_data_has_no_spending_and_no_rows(
    reports: HouseholdReports,
) -> None:
    detail = reports.spending_detail(
        _context(6, date(2026, 6, 3)), _category("groceries"), "month"
    )

    assert (detail.spending, detail.rows) == (None, ())
    assert detail.coverage.status == "no_data"
    assert detail.provisional is not None
    assert detail.provisional.reasons == {"current_month", "late_bookings_unsettled"}


def test_a_year_to_date_gathers_unsettled_months_before_the_selected_one(
    reports: HouseholdReports,
) -> None:
    # June, reference date 2026-06-03: May is unsettled as well as June, and
    # the earlier months' evidence keeps the year to date partial.
    detail = reports.spending_detail(
        _context(6, date(2026, 6, 3)), _category("groceries"), "year_to_date"
    )

    assert detail.provisional is not None
    assert [(m.account_id, m.month) for m in detail.provisional.unsettled] == [
        ("joint-current", ReportingMonth(2026, 5)),
        ("joint-current", ReportingMonth(2026, 6)),
        ("joint-savings", ReportingMonth(2026, 5)),
        ("joint-savings", ReportingMonth(2026, 6)),
    ]
    assert (detail.coverage.status, detail.spending) == ("partial", Decimal("1362.50"))


@pytest.mark.parametrize(
    ("month", "subject"),
    [
        (month, subject)
        for month in range(1, 6)
        for subject in (
            DetailSubject("category", "groceries"),
            DetailSubject("category", "rent"),
            DetailSubject("category", "utilities"),
            DetailSubject("group", "housing"),
            DetailSubject("group", "food"),
        )
    ],
)
def test_a_month_detail_reconciles_to_the_overview(
    reports: HouseholdReports, month: int, subject: DetailSubject
) -> None:
    detail = reports.spending_detail(_context(month), subject, "month")
    overview = reports.monthly_overview(_context(month))

    in_overview = [
        row.spending
        for row in overview.categories
        if subject.id
        == (row.category_id if subject.kind == "category" else row.group_id)
    ]
    assert detail.spending == sum(in_overview, Decimal("0.00"))


def test_an_unknown_subject_is_named_beside_the_contexts_broken_rules(
    reports: HouseholdReports,
) -> None:
    empty = replace(_context(2), account_ids=frozenset())

    with pytest.raises(InvalidSelectionError) as raised:
        reports.spending_detail(empty, DetailSubject("category", "homeware"), "month")

    assert raised.value.reasons == {"no_accounts", "unknown_category"}


@pytest.mark.parametrize(
    "subject",
    [
        DetailSubject("category", "salary"),
        DetailSubject("group", "income"),
        DetailSubject("group", "homeware"),
    ],
)
def test_a_subject_that_is_not_an_expense_category_or_group_is_unknown(
    reports: HouseholdReports, subject: DetailSubject
) -> None:
    with pytest.raises(InvalidSelectionError) as raised:
        reports.spending_detail(_context(2), subject, "month")

    assert raised.value.reasons == {"unknown_category"}
