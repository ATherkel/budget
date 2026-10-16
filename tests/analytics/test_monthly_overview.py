# Copyright 2026 Therkel
"""The monthly overview of `report-contract.md`, over the Gold worked example (#179).

Every expected value is copied from the contract's worked examples, not
derived from the code under test.
"""

from datetime import date
from decimal import Decimal

from budget.analytics import (
    AccountMonthCoverage,
    AccountMonthStatus,
    CategorySpending,
    MoneyInOut,
    MonthlyOverview,
    ReportContext,
    ReportCoverage,
    ReportPublication,
    monthly_overview,
)
from budget.gold import (
    Coverage,
    GoldAccount,
    GoldCategoryAllocation,
    GoldRecords,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from tests.gold.worked_example import CURRENT, PUBLICATION, RECORDS, SAVINGS

GOLD = GoldResult(PUBLICATION, RECORDS)
REFERENCE_DATE = date(2026, 5, 14)

# The contract's "later account": first booked transaction on 2026-04-03.
PERSON = "person-current"
# An account in accounts.toml that has never been imported: no managed period.
NEW = "new-current"


def _account(account_id: str, name: str, *, imported: bool) -> GoldAccount:
    return GoldAccount(
        account_id=account_id,
        display_name=name,
        account_type="current",
        ownership_scope="person" if account_id == PERSON else "household",
        currency="DKK",
        closed_on=None,
        coverage_start=date(2026, 4, 1) if imported else None,
        evidence_through=date(2026, 5, 8) if imported else None,
    )


def _person_row(
    month: int, coverage: Coverage, *, settled: bool
) -> MonthlyBalanceSnapshot:
    return MonthlyBalanceSnapshot(
        account_id=PERSON,
        month=ReportingMonth(2026, month),
        opening_balance=Decimal("1000.00") if month == 4 else None,
        closing_balance=Decimal("800.00") if month == 4 else None,
        coverage=coverage,
        late_bookings_settled=settled,
    )


LATER_GOLD = GoldResult(
    PUBLICATION,
    GoldRecords(
        accounts=(
            *RECORDS.accounts,
            _account(PERSON, "Person current", imported=True),
            _account(NEW, "New current", imported=False),
        ),
        categories=RECORDS.categories,
        transactions=(
            *RECORDS.transactions,
            GoldTransaction(
                transaction_id="person-01",
                account_id=PERSON,
                transaction_date=date(2026, 4, 3),
                account_sequence=1,
                amount=Decimal("-200.00"),
                description="GROCERIES",
                transaction_type="expense",
                transfer_group_id=None,
                balance_after=Decimal("800.00"),
                balance_check="opening",
            ),
        ),
        category_allocations=(
            *RECORDS.category_allocations,
            GoldCategoryAllocation(
                allocation_id="person-01/groceries",
                transaction_id="person-01",
                account_id=PERSON,
                transaction_date=date(2026, 4, 3),
                category_id="groceries",
                amount=Decimal("-200.00"),
            ),
        ),
        monthly_balances=(
            *RECORDS.monthly_balances,
            _person_row(4, "complete", settled=True),
            _person_row(5, "partial", settled=False),
        ),
    ),
)
P1 = ReportPublication(
    publication_id=1,
    kind="pipeline",
    label=None,
    known_at=PUBLICATION.known_at,
    is_current=True,
)
NONE = MoneyInOut(Decimal("0.00"), Decimal("0.00"), 0)


def _context(
    month: int, *account_ids: str, reference_date: date = REFERENCE_DATE
) -> ReportContext:
    return ReportContext(
        publication_id=1,
        account_ids=frozenset(account_ids or (CURRENT, SAVINGS)),
        month=ReportingMonth(2026, month),
        reference_date=reference_date,
    )


def _coverage(gold: GoldResult, context: ReportContext) -> ReportCoverage:
    return monthly_overview(gold, context, is_current=True).coverage


def test_february_nets_the_refund_and_names_the_partial_account() -> None:
    context = _context(2)

    assert monthly_overview(GOLD, context, is_current=True) == MonthlyOverview(
        context=context,
        publication=P1,
        currency="DKK",
        income=Decimal("25000.00"),
        expenses=Decimal("9020.00"),
        net_cash_flow=Decimal("15980.00"),
        savings_rate=Decimal("0.6392"),
        categories=(
            CategorySpending("rent", "Rent", "housing", "Housing", Decimal("8500.00")),
            CategorySpending(
                "groceries", "Groceries", "food", "Food", Decimal("520.00")
            ),
        ),
        unclassified=NONE,
        adjustments=NONE,
        coverage=ReportCoverage(
            status="partial",
            account_months=(
                AccountMonthCoverage(
                    CURRENT, "Joint current", ReportingMonth(2026, 2), "partial"
                ),
            ),
        ),
        provisional=None,
    )


def _month(
    account_id: str, name: str, month: int, status: AccountMonthStatus
) -> AccountMonthCoverage:
    return AccountMonthCoverage(account_id, name, ReportingMonth(2026, month), status)


def test_a_month_before_an_account_existed_never_makes_coverage_partial() -> None:
    # report-contract.md, "A later account: outside_history".
    assert _coverage(LATER_GOLD, _context(2, SAVINGS, PERSON)) == ReportCoverage(
        status="complete",
        account_months=(_month(PERSON, "Person current", 2, "outside_history"),),
    )


def test_evidence_for_one_account_but_not_another_is_partial() -> None:
    # joint-savings is complete in March; new-current was never imported.
    assert _coverage(LATER_GOLD, _context(3, SAVINGS, NEW)) == ReportCoverage(
        status="partial",
        account_months=(_month(NEW, "New current", 3, "no_data"),),
    )


def test_a_quiet_month_with_every_account_complete_is_complete() -> None:
    # report-contract.md, "March, joint-savings only: a confirmed quiet month".
    assert _coverage(GOLD, _context(3, SAVINGS)) == ReportCoverage(
        status="complete", account_months=()
    )


def test_a_month_after_the_latest_published_month_is_no_data() -> None:
    # report-contract.md, "June, reference date 2026-06-03: no data".
    context = _context(6, reference_date=date(2026, 6, 3))

    assert _coverage(GOLD, context) == ReportCoverage(
        status="no_data",
        account_months=(
            _month(CURRENT, "Joint current", 6, "no_data"),
            _month(SAVINGS, "Joint savings", 6, "no_data"),
        ),
    )


def test_a_selection_with_no_contributing_account_month_is_no_data() -> None:
    # person-current alone, before its history starts: nothing contributes.
    assert _coverage(LATER_GOLD, _context(2, PERSON)) == ReportCoverage(
        status="no_data",
        account_months=(_month(PERSON, "Person current", 2, "outside_history"),),
    )


def test_a_partial_account_stays_partial_beside_one_without_history() -> None:
    assert _coverage(LATER_GOLD, _context(2, CURRENT, PERSON)) == ReportCoverage(
        status="partial",
        account_months=(
            _month(CURRENT, "Joint current", 2, "partial"),
            _month(PERSON, "Person current", 2, "outside_history"),
        ),
    )


def test_no_evidence_stays_no_data_beside_an_account_without_history() -> None:
    assert _coverage(LATER_GOLD, _context(2, NEW, PERSON)) == ReportCoverage(
        status="no_data",
        account_months=(
            _month(NEW, "New current", 2, "no_data"),
            _month(PERSON, "Person current", 2, "outside_history"),
        ),
    )


def test_partial_evidence_beside_no_evidence_is_partial() -> None:
    assert _coverage(LATER_GOLD, _context(2, CURRENT, NEW)) == ReportCoverage(
        status="partial",
        account_months=(
            _month(CURRENT, "Joint current", 2, "partial"),
            _month(NEW, "New current", 2, "no_data"),
        ),
    )
