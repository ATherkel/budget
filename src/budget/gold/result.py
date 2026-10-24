# Copyright 2026 Therkel
"""`GoldResult`: one build's Gold records, answering both interfaces in memory."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, fields
from datetime import date

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
        _copy_collections(self)


@dataclass(frozen=True)
class GoldLineageRecords:
    """The privileged lineage records of one build; never for analytics."""

    classification_review_items: Sequence[ClassificationReviewItem] = ()
    transaction_lineage: Sequence[GoldTransactionLineage] = ()

    def __post_init__(self) -> None:
        """Copy each collection, so a caller's later change never reaches Gold."""
        _copy_collections(self)


def _copy_collections(records: GoldRecords | GoldLineageRecords) -> None:
    """Replace each collection of frozen records with a tuple copy."""
    for record_kind in fields(records):
        copied = tuple(getattr(records, record_kind.name))
        # A frozen dataclass sets its own fields only through object.
        object.__setattr__(records, record_kind.name, copied)


def refuse_bare_string(account_ids: Collection[str] | None) -> None:
    """Raise `TypeError` for a str, which `in` would search for substrings.

    The check runs before any record is read, so a query matching no records
    refuses it too.
    """
    if isinstance(account_ids, str):
        message = "account_ids takes a collection of account ids, not one str"
        raise TypeError(message)


def _named(account_id: str, account_ids: Collection[str] | None) -> bool:
    """Whether `account_ids` names `account_id`; `None` names every account."""
    return account_ids is None or account_id in account_ids


class GoldResult:
    """One build's records, bound to one publication.

    It is both a `GoldRepository` and a `GoldLineageRepository`. Analytics tests
    build one from synthetic records, so they need neither a store nor the Gold
    build.
    """

    __slots__ = ("_lineage", "_publication", "_records")

    def __init__(
        self,
        publication: GoldPublication,
        records: GoldRecords,
        lineage: GoldLineageRecords | None = None,
    ) -> None:
        """Bind `records` and `lineage` to `publication`; no lineage is empty."""
        self._publication = publication
        self._records = records
        self._lineage = GoldLineageRecords() if lineage is None else lineage

    @property
    def records(self) -> GoldRecords:
        """Every record of the build, for a store that persists the result."""
        return self._records

    @property
    def lineage(self) -> GoldLineageRecords:
        """Every lineage record of the build, for a store that persists them."""
        return self._lineage

    def publication(self) -> GoldPublication:
        """Return the publication these records belong to."""
        return self._publication

    def accounts(self) -> Sequence[GoldAccount]:
        """Return every account inside the reporting boundary."""
        return self._records.accounts

    def categories(self) -> Sequence[GoldCategory]:
        """Return every assignable category."""
        return self._records.categories

    def transactions(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldTransaction]:
        """Return the transactions dated from `start_date` through `end_date`."""
        refuse_bare_string(account_ids)
        return tuple(
            transaction
            for transaction in self._records.transactions
            if start_date <= transaction.transaction_date <= end_date
            and _named(transaction.account_id, account_ids)
        )

    def category_allocations(
        self,
        *,
        start_date: date,
        end_date: date,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[GoldCategoryAllocation]:
        """Return the allocations dated from `start_date` through `end_date`."""
        refuse_bare_string(account_ids)
        return tuple(
            allocation
            for allocation in self._records.category_allocations
            if start_date <= allocation.transaction_date <= end_date
            and _named(allocation.account_id, account_ids)
        )

    def monthly_balances(
        self,
        *,
        start_month: ReportingMonth,
        end_month: ReportingMonth,
        account_ids: Collection[str] | None = None,
    ) -> Sequence[MonthlyBalanceSnapshot]:
        """Return the snapshots for `start_month` through `end_month`."""
        refuse_bare_string(account_ids)
        return tuple(
            snapshot
            for snapshot in self._records.monthly_balances
            if start_month <= snapshot.month <= end_month
            and _named(snapshot.account_id, account_ids)
        )

    def transaction_lineage(
        self, transaction_ids: Collection[str]
    ) -> Sequence[GoldTransactionLineage]:
        """Return the lineage of each named transaction."""
        if isinstance(transaction_ids, str):
            message = "transaction_ids takes a collection of ids, not one str"
            raise TypeError(message)
        return tuple(
            line
            for line in self._lineage.transaction_lineage
            if line.transaction_id in transaction_ids
        )

    def classification_review_items(self) -> Sequence[ClassificationReviewItem]:
        """Return every open classification review item."""
        return self._lineage.classification_review_items
