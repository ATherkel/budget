# Copyright 2026 Therkel
"""The synthetic worked example of `docs/architecture/gold-layer.md` as Gold records.

Every account, text and amount here is invented. Transaction identifiers name
the account and the doc's `seq` (`current-04` is row 4 of the `joint-current`
table), and an allocation's identifier joins its transaction and category, as
the contract derives it from the two. `test_worked_example.py` fails when these
records and the doc's tables drift apart.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import NamedTuple

from budget.gold import (
    BalanceCheck,
    Coverage,
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldPublication,
    GoldRecords,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
    TransactionType,
)

CURRENT = "joint-current"
SAVINGS = "joint-savings"

PUBLICATION = GoldPublication(
    publication_id=1,
    kind="pipeline",
    label=None,
    known_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
    built_at=datetime(2026, 5, 9, 8, 0, tzinfo=UTC),
    replayed_at=None,
    contract_version="0.2",
    fingerprint_scheme="synthetic",
    result_fingerprint="0" * 64,
)

# One admitted export, dated 2026-05-08, covers 2026-01-01 through 2026-05-08.
ACCOUNTS = (
    GoldAccount(
        account_id=CURRENT,
        display_name="Joint current",
        account_type="current",
        ownership_scope="household",
        currency="DKK",
        closed_on=None,
        coverage_start=date(2026, 1, 1),
        evidence_through=date(2026, 5, 8),
    ),
    GoldAccount(
        account_id=SAVINGS,
        display_name="Joint savings",
        account_type="savings",
        ownership_scope="household",
        currency="DKK",
        closed_on=None,
        coverage_start=date(2026, 1, 1),
        evidence_through=date(2026, 5, 8),
    ),
)

CATEGORIES = (
    GoldCategory("salary", "Salary", "income", "Income", "income"),
    GoldCategory("interest", "Interest", "income", "Income", "income"),
    GoldCategory("rent", "Rent", "housing", "Housing", "expense"),
    GoldCategory("utilities", "Utilities", "housing", "Housing", "expense"),
    GoldCategory("groceries", "Groceries", "food", "Food", "expense"),
)


class _Row(NamedTuple):
    """One row of the example's transaction tables."""

    seq: int
    transaction_date: str
    amount: str
    transaction_type: TransactionType
    category_id: str | None
    balance_after: str
    transfer_group_id: str | None = None
    balance_check: BalanceCheck = "consistent"


_CURRENT_ROWS = (
    _Row(1, "2026-01-14", "25000.00", "income", "salary", "25400.00", None, "opening"),
    _Row(2, "2026-01-20", "-3000.00", "transfer", None, "22400.00", "T1"),
    _Row(3, "2026-01-28", "-842.50", "expense", "groceries", "21557.50"),
    _Row(4, "2026-02-02", "-8500.00", "expense", "rent", "13057.50"),
    _Row(5, "2026-02-02", "-640.00", "expense", "groceries", "12417.50"),
    _Row(6, "2026-02-12", "120.00", "refund", "groceries", "12537.50"),
    _Row(7, "2026-02-25", "25000.00", "income", "salary", "37537.50"),
    _Row(8, "2026-03-02", "-450.00", "unknown", None, "36587.50", None, "break"),
    _Row(9, "2026-03-20", "-1000.00", "expense", "utilities", "35587.50"),
    _Row(10, "2026-04-01", "-8500.00", "expense", "rent", "27087.50"),
    _Row(11, "2026-04-24", "25000.00", "income", "salary", "52087.50"),
)

_SAVINGS_ROWS = (
    _Row(1, "2026-01-20", "3000.00", "transfer", None, "53000.00", "T1", "opening"),
    _Row(2, "2026-04-30", "12.40", "income", "interest", "53012.40"),
)

_BOOKED = tuple((CURRENT, row) for row in _CURRENT_ROWS) + tuple(
    (SAVINGS, row) for row in _SAVINGS_ROWS
)


def _transaction_id(account_id: str, seq: int) -> str:
    return f"{'current' if account_id == CURRENT else 'savings'}-{seq:02d}"


def _transaction(account_id: str, row: _Row) -> GoldTransaction:
    return GoldTransaction(
        transaction_id=_transaction_id(account_id, row.seq),
        account_id=account_id,
        transaction_date=date.fromisoformat(row.transaction_date),
        account_sequence=row.seq,
        amount=Decimal(row.amount),
        description=(row.category_id or row.transaction_type).upper(),
        transaction_type=row.transaction_type,
        transfer_group_id=row.transfer_group_id,
        balance_after=Decimal(row.balance_after),
        balance_check=row.balance_check,
    )


def _allocation(account_id: str, row: _Row, category_id: str) -> GoldCategoryAllocation:
    transaction_id = _transaction_id(account_id, row.seq)
    return GoldCategoryAllocation(
        allocation_id=f"{transaction_id}/{category_id}",
        transaction_id=transaction_id,
        account_id=account_id,
        transaction_date=date.fromisoformat(row.transaction_date),
        category_id=category_id,
        amount=Decimal(row.amount),
    )


TRANSACTIONS = tuple(_transaction(account_id, row) for account_id, row in _BOOKED)

# Each classified transaction's single allocation, for its whole amount.
CATEGORY_ALLOCATIONS = tuple(
    _allocation(account_id, row, row.category_id)
    for account_id, row in _BOOKED
    if row.category_id is not None
)


def _snapshot(
    account_id: str,
    month: int,
    balances: tuple[str, str] | None,
    coverage: Coverage,
) -> MonthlyBalanceSnapshot:
    opening, closing = balances or (None, None)
    return MonthlyBalanceSnapshot(
        account_id=account_id,
        month=ReportingMonth(2026, month),
        opening_balance=None if opening is None else Decimal(opening),
        closing_balance=None if closing is None else Decimal(closing),
        coverage=coverage,
        # The only export, dated 2026-05-08, settles April but not May.
        late_bookings_settled=month <= 4,
    )


MONTHLY_BALANCES = (
    _snapshot(CURRENT, 1, ("400.00", "21557.50"), "partial"),
    _snapshot(CURRENT, 2, ("21557.50", "37537.50"), "partial"),
    _snapshot(CURRENT, 3, ("37037.50", "35587.50"), "partial"),
    _snapshot(CURRENT, 4, ("35587.50", "52087.50"), "complete"),
    _snapshot(CURRENT, 5, None, "partial"),
    _snapshot(SAVINGS, 1, ("50000.00", "53000.00"), "partial"),
    _snapshot(SAVINGS, 2, ("53000.00", "53000.00"), "complete"),
    _snapshot(SAVINGS, 3, ("53000.00", "53000.00"), "complete"),
    _snapshot(SAVINGS, 4, ("53000.00", "53012.40"), "complete"),
    _snapshot(SAVINGS, 5, None, "partial"),
)

RECORDS = GoldRecords(
    accounts=ACCOUNTS,
    categories=CATEGORIES,
    transactions=TRANSACTIONS,
    category_allocations=CATEGORY_ALLOCATIONS,
    monthly_balances=MONTHLY_BALANCES,
)


def example_transactions(*transaction_ids: str) -> list[GoldTransaction]:
    """Return the example's transactions with these identifiers (`current-04`)."""
    by_id = {t.transaction_id: t for t in TRANSACTIONS}
    return [by_id[transaction_id] for transaction_id in transaction_ids]


def example_allocations(*allocation_ids: str) -> list[GoldCategoryAllocation]:
    """Return the example's allocations with these identifiers (`current-04/rent`)."""
    by_id = {a.allocation_id: a for a in CATEGORY_ALLOCATIONS}
    return [by_id[allocation_id] for allocation_id in allocation_ids]


def example_balances(account_id: str, *months: int) -> list[MonthlyBalanceSnapshot]:
    """Return the example's snapshots of `account_id` for these months of 2026."""
    by_key = {(s.account_id, s.month): s for s in MONTHLY_BALANCES}
    return [by_key[account_id, ReportingMonth(2026, month)] for month in months]
