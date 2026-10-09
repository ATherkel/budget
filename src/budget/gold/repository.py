# Copyright 2026 Therkel
"""The Gold consumer and lineage interfaces; every date and month range is inclusive."""

from collections.abc import Collection, Sequence
from datetime import date
from typing import Protocol

from budget.gold.models import (
    ClassificationReviewItem,
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldPublication,
    GoldTransaction,
    GoldTransactionLineage,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)


class GoldRepository(Protocol):
    """One publication's consumer records.

    `account_ids=None` means every account, and an empty collection means none.
    """

    def publication(self) -> GoldPublication:
        """Return the publication every other method reads from."""
        ...

    def accounts(self) -> Sequence[GoldAccount]:
        """Return every account inside the reporting boundary."""
        ...

    def categories(self) -> Sequence[GoldCategory]:
        """Return every assignable category."""
        ...

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldTransaction]:
        """Return the transactions dated from `start_date` through `end_date`."""
        ...

    def category_allocations(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldCategoryAllocation]:
        """Return the allocations dated from `start_date` through `end_date`."""
        ...

    def monthly_balances(
        self,
        *,
        start_month: ReportingMonth,
        end_month: ReportingMonth,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[MonthlyBalanceSnapshot]:
        """Return the snapshots for `start_month` through `end_month`."""
        ...


class GoldLineageRepository(Protocol):
    """Privileged lineage for review and audit tooling; never for analytics."""

    def transaction_lineage(
        self, transaction_ids: Collection[str]
    ) -> Sequence[GoldTransactionLineage]:
        """Return the lineage of each named transaction."""
        ...

    def classification_review_items(self) -> Sequence[ClassificationReviewItem]:
        """Return every open classification review item."""
        ...
