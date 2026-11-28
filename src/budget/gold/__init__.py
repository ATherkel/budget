# Copyright 2026 Therkel
"""Gold contract 0.2: its records, its interfaces, and `GoldResult`.

`budget.gold` is the seam analytics imports. The normative schema is
`docs/architecture/gold-contract.md`.
"""

from budget.gold.build import build
from budget.gold.models import (
    AccountType,
    BalanceCheck,
    CategoryDirection,
    Classification,
    ClassificationReviewItem,
    ClassificationReviewKind,
    ClassificationSource,
    Coverage,
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldOwner,
    GoldPublication,
    GoldTransaction,
    GoldTransactionLineage,
    MonthlyBalanceSnapshot,
    PublicationKind,
    ReportingMonth,
    TransactionType,
    TransferBasis,
    TransferEvidence,
)
from budget.gold.months import first_day, last_day, months_through
from budget.gold.repository import (
    GoldLineageRepository,
    GoldPublications,
    GoldRepository,
    GoldStoreClosedError,
    GoldStoreLifecycleError,
    GoldStoreReadOnlyError,
    GoldStoreThreadError,
    PublicationUnavailableError,
)
from budget.gold.result import GoldLineageRecords, GoldRecords, GoldResult
from budget.gold.store import UndoUnavailableError

__all__ = [
    "AccountType",
    "BalanceCheck",
    "CategoryDirection",
    "Classification",
    "ClassificationReviewItem",
    "ClassificationReviewKind",
    "ClassificationSource",
    "Coverage",
    "GoldAccount",
    "GoldCategory",
    "GoldCategoryAllocation",
    "GoldLineageRecords",
    "GoldLineageRepository",
    "GoldOwner",
    "GoldPublication",
    "GoldPublications",
    "GoldRecords",
    "GoldRepository",
    "GoldResult",
    "GoldStoreClosedError",
    "GoldStoreLifecycleError",
    "GoldStoreReadOnlyError",
    "GoldStoreThreadError",
    "GoldTransaction",
    "GoldTransactionLineage",
    "MonthlyBalanceSnapshot",
    "PublicationKind",
    "PublicationUnavailableError",
    "ReportingMonth",
    "TransactionType",
    "TransferBasis",
    "TransferEvidence",
    "UndoUnavailableError",
    "build",
    "first_day",
    "last_day",
    "months_through",
]
