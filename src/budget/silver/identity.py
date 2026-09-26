# Copyright 2026 Therkel
"""Transaction identity, as `silver-layer.md` (*Identity and merging*) defines it."""

import hashlib
import json
from datetime import date
from decimal import Decimal

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
    """Hash the identity inputs, serialised as a compact JSON array, with SHA-256."""
    inputs = [
        IDENTITY_VERSION,
        account_id,
        transaction_date.isoformat(),
        written(amount),
        description,
        occurrence,
    ]
    serialised = json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialised.encode()).hexdigest()
