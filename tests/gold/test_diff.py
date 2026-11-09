# Copyright 2026 Therkel
"""Publication diffs read each result through the public Gold interface."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from budget.gold import (
    ClassificationReviewItem,
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldResult,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
    TransactionType,
)
from budget.gold.diff import compare_publications
from tests.gold.worked_example import PUBLICATION, RECORDS

ACCOUNT = GoldAccount(
    account_id="joint-current",
    display_name="Joint current",
    account_type="current",
    ownership_scope="household",
    currency="DKK",
    closed_on=None,
    coverage_start=date(2026, 2, 1),
    evidence_through=date(2026, 2, 28),
)
CATEGORIES = (
    GoldCategory("salary", "Salary", "income", "Income", "income"),
    GoldCategory("groceries", "Groceries", "food", "Food", "expense"),
    GoldCategory("housing", "Housing", "home", "Home", "expense"),
)


def _transaction(
    transaction_id: str,
    amount: str,
    transaction_type: TransactionType,
    sequence: int,
) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=transaction_id,
        account_id=ACCOUNT.account_id,
        transaction_date=date(2026, 2, sequence),
        account_sequence=sequence,
        amount=Decimal(amount),
        description=transaction_id,
        transaction_type=transaction_type,
        transfer_group_id=None,
        balance_after=None,
        balance_check="missing_balance",
    )


def _allocation(
    transaction_id: str,
    category_id: str,
    amount: str,
    sequence: int,
) -> GoldCategoryAllocation:
    return GoldCategoryAllocation(
        allocation_id=f"{transaction_id}-{category_id}",
        transaction_id=transaction_id,
        account_id=ACCOUNT.account_id,
        transaction_date=date(2026, 2, sequence),
        category_id=category_id,
        amount=Decimal(amount),
    )


PREVIOUS = GoldResult(
    replace(PUBLICATION, publication_id=1),
    replace(
        RECORDS,
        accounts=(ACCOUNT,),
        categories=CATEGORIES,
        transactions=(
            _transaction("salary-before", "1000.00", "income", 1),
            _transaction("groceries-before", "-250.00", "expense", 2),
            _transaction("refund-before", "50.00", "refund", 3),
            _transaction("unknown-before", "-30.00", "unknown", 4),
        ),
        category_allocations=(
            _allocation("salary-before", "salary", "1000.00", 1),
            _allocation("groceries-before", "groceries", "-250.00", 2),
            _allocation("refund-before", "groceries", "50.00", 3),
        ),
        monthly_balances=(
            MonthlyBalanceSnapshot(
                account_id=ACCOUNT.account_id,
                month=ReportingMonth(2026, 2),
                opening_balance=None,
                closing_balance=None,
                coverage="partial",
                late_bookings_settled=False,
            ),
        ),
    ),
)
CURRENT = GoldResult(
    replace(PUBLICATION, publication_id=2),
    replace(
        RECORDS,
        accounts=(ACCOUNT,),
        categories=CATEGORIES,
        transactions=(
            _transaction("salary-after", "1200.00", "income", 1),
            _transaction("groceries-after", "-350.00", "expense", 2),
            _transaction("refund-after", "50.00", "refund", 3),
            _transaction("housing-after", "-100.00", "expense", 4),
            _transaction("unknown-out", "-80.00", "unknown", 5),
            _transaction("unknown-in", "10.00", "unknown", 6),
        ),
        category_allocations=(
            _allocation("salary-after", "salary", "1200.00", 1),
            _allocation("groceries-after", "groceries", "-350.00", 2),
            _allocation("refund-after", "groceries", "50.00", 3),
            _allocation("housing-after", "housing", "-100.00", 4),
        ),
        monthly_balances=(
            MonthlyBalanceSnapshot(
                account_id=ACCOUNT.account_id,
                month=ReportingMonth(2026, 2),
                opening_balance=None,
                closing_balance=None,
                coverage="partial",
                late_bookings_settled=False,
            ),
        ),
    ),
)


def test_diff_reports_changed_money_measures_for_each_month_and_account() -> None:
    assert compare_publications(PREVIOUS, CURRENT) == (
        (
            "Changes  2026-02 joint-current: income +200.00 DKK; "
            "expenses +200.00 DKK; category groceries +100.00 DKK; "
            "category housing +100.00 DKK; category salary +200.00 DKK; "
            "group food +100.00 DKK; group home +100.00 DKK; "
            "group income +200.00 DKK; unclassified in +10.00 DKK; "
            "unclassified out -50.00 DKK; unclassified count +1"
        ),
    )


def test_diff_reports_changed_coverage_for_each_month_and_account() -> None:
    before = GoldResult(
        replace(CURRENT.publication(), publication_id=1),
        CURRENT.records,
    )
    after = GoldResult(
        replace(CURRENT.publication(), publication_id=2),
        replace(
            CURRENT.records,
            monthly_balances=(
                replace(
                    CURRENT.records.monthly_balances[0],
                    coverage="complete",
                ),
            ),
        ),
    )

    assert compare_publications(before, after) == (
        "Changes  2026-02 joint-current: coverage partial -> complete",
    )


def test_diff_reports_review_items_opened_and_closed() -> None:
    closed = ClassificationReviewItem(
        review_item_id="a" * 64,
        kind="unclassified",
        transaction_ids=(),
        rule_ids=(),
        decision_id=None,
        reason=None,
    )
    opened = ClassificationReviewItem(
        review_item_id="b" * 64,
        kind="rule-conflict",
        transaction_ids=(),
        rule_ids=(),
        decision_id=None,
        reason=None,
    )
    before = GoldResult(
        replace(CURRENT.publication(), publication_id=1),
        CURRENT.records,
    )
    after = GoldResult(
        replace(CURRENT.publication(), publication_id=2),
        CURRENT.records,
    )

    assert compare_publications(
        before,
        after,
        previous_reviews=(closed,),
        current_reviews=(opened,),
    ) == ("Review  1 rule-conflict opened; 1 unclassified closed",)


def test_unclassified_money_removed_from_either_direction_is_a_signed_delta() -> None:
    after = GoldResult(
        replace(CURRENT.publication(), publication_id=3),
        replace(
            CURRENT.records,
            transactions=tuple(
                transaction
                for transaction in CURRENT.records.transactions
                if not transaction.transaction_id.startswith("unknown-")
            ),
        ),
    )

    assert compare_publications(CURRENT, after) == (
        (
            "Changes  2026-02 joint-current: unclassified in -10.00 DKK; "
            "unclassified out +80.00 DKK; unclassified count -2"
        ),
    )


def test_a_zero_net_category_change_does_not_emit_an_empty_change_line() -> None:
    old = GoldCategory("old", "Old", "old-group", "Old group", "expense")
    new = GoldCategory("new", "New", "new-group", "New group", "expense")
    transactions = (
        _transaction("positive", "50.00", "refund", 1),
        _transaction("negative", "-50.00", "expense", 2),
    )
    before = GoldResult(
        replace(PUBLICATION, publication_id=1),
        replace(
            RECORDS,
            accounts=(ACCOUNT,),
            categories=(old,),
            transactions=transactions,
            category_allocations=(
                _allocation("positive", "old", "50.00", 1),
                _allocation("negative", "old", "-50.00", 2),
            ),
            monthly_balances=(),
        ),
    )
    after = GoldResult(
        replace(PUBLICATION, publication_id=2),
        replace(
            RECORDS,
            accounts=(ACCOUNT,),
            categories=(new,),
            transactions=transactions,
            category_allocations=(
                _allocation("positive", "new", "50.00", 1),
                _allocation("negative", "new", "-50.00", 2),
            ),
            monthly_balances=(),
        ),
    )

    assert compare_publications(before, after) == ()


def test_changed_measures_remain_separate_by_account_and_month() -> None:
    savings = replace(
        ACCOUNT,
        account_id="joint-savings",
        display_name="Joint savings",
    )
    groceries = CATEGORIES[1]
    january_current = replace(
        _transaction("january-current", "-10.00", "expense", 1),
        transaction_date=date(2026, 1, 1),
    )
    january_savings = replace(
        _transaction("january-savings", "-20.00", "expense", 1),
        account_id=savings.account_id,
        transaction_date=date(2026, 1, 1),
    )
    february_current = replace(
        _transaction("february-current", "-30.00", "expense", 1),
        transaction_date=date(2026, 2, 1),
    )
    before = GoldResult(
        replace(PUBLICATION, publication_id=1),
        replace(
            RECORDS,
            accounts=(ACCOUNT, savings),
            categories=(groceries,),
            transactions=(),
            category_allocations=(),
            monthly_balances=(),
        ),
    )
    after = GoldResult(
        replace(PUBLICATION, publication_id=2),
        replace(
            RECORDS,
            accounts=(ACCOUNT, savings),
            categories=(groceries,),
            transactions=(january_current, january_savings, february_current),
            category_allocations=(
                replace(
                    _allocation("january-current", "groceries", "-10.00", 1),
                    transaction_date=date(2026, 1, 1),
                ),
                replace(
                    _allocation("january-savings", "groceries", "-20.00", 1),
                    account_id=savings.account_id,
                    transaction_date=date(2026, 1, 1),
                ),
                replace(
                    _allocation("february-current", "groceries", "-30.00", 1),
                    transaction_date=date(2026, 2, 1),
                ),
            ),
            monthly_balances=(),
        ),
    )

    assert compare_publications(before, after) == (
        (
            "Changes  2026-01 joint-current: expenses +10.00 DKK; "
            "category groceries +10.00 DKK; group food +10.00 DKK"
        ),
        (
            "Changes  2026-01 joint-savings: expenses +20.00 DKK; "
            "category groceries +20.00 DKK; group food +20.00 DKK"
        ),
        (
            "Changes  2026-02 joint-current: expenses +30.00 DKK; "
            "category groceries +30.00 DKK; group food +30.00 DKK"
        ),
    )
