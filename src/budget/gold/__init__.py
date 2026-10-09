# Copyright 2026 Therkel
"""Gold contract 0.2: its records, its interfaces, and `GoldResult`.

`budget.gold` is the seam analytics imports. The normative schema is
`docs/architecture/gold-contract.md`.
"""

from budget.gold.models import (
    AccountType,
    BalanceCheck,
    CategoryDirection,
    ClassificationReviewItem,
    ClassificationReviewKind,
    ClassificationSource,
    Coverage,
    GoldAccount,
    GoldCategory,
    GoldCategoryAllocation,
    GoldPublication,
    GoldTransaction,
    GoldTransactionLineage,
    MonthlyBalanceSnapshot,
    OwnershipScope,
    PublicationKind,
    ReportingMonth,
    TransactionType,
    TransferBasis,
    TransferEvidence,
)
from budget.gold.repository import GoldLineageRepository, GoldRepository
from budget.gold.result import GoldRecords, GoldResult

__all__ = [
    "AccountType",
    "BalanceCheck",
    "CategoryDirection",
    "ClassificationReviewItem",
    "ClassificationReviewKind",
    "ClassificationSource",
    "Coverage",
    "GoldAccount",
    "GoldCategory",
    "GoldCategoryAllocation",
    "GoldLineageRepository",
    "GoldPublication",
    "GoldRecords",
    "GoldRepository",
    "GoldResult",
    "GoldTransaction",
    "GoldTransactionLineage",
    "MonthlyBalanceSnapshot",
    "OwnershipScope",
    "PublicationKind",
    "ReportingMonth",
    "TransactionType",
    "TransferBasis",
    "TransferEvidence",
]
