# Copyright 2026 Therkel
"""`GoldResult`: one build's Gold records, answering `GoldRepository` in memory."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, fields
from datetime import date

from budget.gold.models import (
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldPublication,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)


@dataclass(frozen=True)
class GoldRecords:
    """The consumer records of one build; a kind left unnamed is empty."""

    accounts: Sequence[GoldAccount] = ()
    categories: Sequence[GoldCategory] = ()
    transactions: Sequence[GoldTransaction] = ()
    category_allocations: Sequence[GoldCategoryAllocation] = ()
    monthly_balances: Sequence[MonthlyBalanceSnapshot] = ()

    def __post_init__(self) -> None:
        """Copy each collection, so a caller's later change never reaches Gold."""
        for record_kind in fields(self):
            copied = tuple(getattr(self, record_kind.name))
            # A frozen dataclass sets its own fields only through object.
            object.__setattr__(self, record_kind.name, copied)


class GoldResult:
    """One build's records, bound to one publication; a `GoldRepository`.

    Analytics tests build one from synthetic records, so they need neither a
    store nor the Gold build.
    """

    __slots__ = ("_publication", "_records")

    def __init__(self, publication: GoldPublication, records: GoldRecords) -> None:
        """Bind `records` to `publication`."""
        self._publication = publication
        self._records = records

    def publication(self) -> GoldPublication:
        """Return the publication these records belong to."""
        return self._publication

    def accounts(self) -> Sequence[GoldAccount]:
        """Return every account inside the reporting boundary."""
        return ()

    def categories(self) -> Sequence[GoldCategory]:
        """Return every assignable category."""
        return ()

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldTransaction]:
        """Return the transactions dated from `start_date` through `end_date`."""
        del account_ids
        return tuple(
            transaction
            for transaction in self._records.transactions
            if start_date <= transaction.transaction_date <= end_date
        )

    def category_allocations(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldCategoryAllocation]:
        """Return the allocations dated from `start_date` through `end_date`."""
        del start_date, end_date, account_ids
        return ()

    def monthly_balances(
        self,
        *,
        start_month: ReportingMonth,
        end_month: ReportingMonth,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[MonthlyBalanceSnapshot]:
        """Return the snapshots for `start_month` through `end_month`."""
        del start_month, end_month, account_ids
        return ()
