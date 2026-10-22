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
    A bare `str` raises `TypeError`, since it is a collection of strings too.
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


class PublicationUnavailableError(LookupError):
    """The publication does not exist, or its result is no longer retained."""

    def __init__(self, publication_id: int) -> None:
        """Name the publication that cannot be read."""
        super().__init__(
            f"publication {publication_id} is not available: it does not exist "
            "or its result is no longer retained"
        )


class GoldStoreLifecycleError(RuntimeError):
    """Base class for use of a Gold store outside its supported lifetime."""


class GoldStoreClosedError(GoldStoreLifecycleError):
    """The Gold store has already been closed."""

    def __init__(self) -> None:
        """Say how to make another request."""
        super().__init__(
            "the Gold store is closed; open a new store within this request"
        )


class GoldStoreThreadError(GoldStoreLifecycleError):
    """The Gold store was used from a thread other than its creating thread."""

    def __init__(self) -> None:
        """Say where the replacement store must be opened."""
        super().__init__(
            "the Gold store was used from another thread; open a new store "
            "inside the thread that reads it"
        )


class GoldStoreReadOnlyError(RuntimeError):
    """A write was attempted through a read-only Gold store."""

    def __init__(self) -> None:
        """Name the mode publishing needs."""
        super().__init__(
            "the Gold store was opened read-only; publishing needs a writable store"
        )


class GoldPublications(Protocol):
    """The retained publications of one request-scoped Gold store.

    The implementation owns one connection. Open, use, and close it on the
    thread that created it within one synchronous request or task. Do not
    cache or share the object across server threads. A repository returned by
    `open()` borrows the same owner and cannot be used after that owner closes.
    """

    def current(self) -> GoldPublication | None:
        """Return the current publication, or None when there is none."""
        ...

    def available(self) -> Sequence[GoldPublication]:
        """Return the publications whose results are retained."""
        ...

    def open(self, publication_id: int) -> GoldRepository:
        """Return a repository bound to one publication.

        Raises `PublicationUnavailableError` when the publication does not exist or
        its result is not retained.
        """
        ...
