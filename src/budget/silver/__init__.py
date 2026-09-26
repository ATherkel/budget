# Copyright 2026 Therkel
"""Public Silver contracts and the Silver build.

`budget.silver` is the seam the rest of the application imports: `build` turns
Bronze import runs into validated, source-neutral canonical records.
"""

from budget.silver.build import build
from budget.silver.decisions import AcceptDiscrepancy, SilverDecision
from budget.silver.models import (
    AccountEvidence,
    BalanceObservation,
    ImportRunResult,
    ReviewItem,
    SilverResult,
    Transaction,
    TransactionEvidence,
    UnbookedRecord,
    ValidationError,
)

__all__ = [
    "AcceptDiscrepancy",
    "AccountEvidence",
    "BalanceObservation",
    "ImportRunResult",
    "ReviewItem",
    "SilverDecision",
    "SilverResult",
    "Transaction",
    "TransactionEvidence",
    "UnbookedRecord",
    "ValidationError",
    "build",
]
