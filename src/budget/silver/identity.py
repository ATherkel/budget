# Copyright 2026 Therkel
"""Transaction identity, as `silver-layer.md` (*Identity and merging*) defines it."""

from datetime import date
from decimal import Decimal

from budget.hashing import hash_parts
from budget.silver.currencies import written

IDENTITY_VERSION = "1"


def identity_text(text: str) -> str:
    """Trim Unicode whitespace, 0xA0 included, and collapse internal runs."""
    return " ".join(text.split())


def transaction_id(
    account_id: str,
    transaction_date: date,
    amount: Decimal,
    description: str,
    occurrence: int,
) -> str:
    """Hash the ADR-009 identity inputs."""
    return hash_parts(
        [
            IDENTITY_VERSION,
            account_id,
            transaction_date.isoformat(),
            written(amount),
            description,
            occurrence,
        ]
    )


def review_item_id(kind: str, import_run_id: str, *transaction_id: str) -> str:
    """Hash a review item's kind, the run that raised it, and what it drops."""
    return hash_parts([kind, import_run_id, *transaction_id])
