# Copyright 2026 Therkel
"""The result fingerprint of one publication (`publications.md`, *The Recipe*).

A SHA-256 over a canonical serialization of every record the publication
returns through `GoldRepository` and `GoldLineageRepository`, each kind in key
order. The publication's own metadata, such as `built_at`, takes no part.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Final

from budget.gold.result import GoldResult
from budget.inputs.snapshot import canonical_amount

CONTRACT_VERSION: Final = "0.2"
FINGERPRINT_SCHEME: Final = "1"


def result_fingerprint(result: GoldResult) -> str:
    """Return the hex SHA-256 of `result`'s records under the current scheme."""
    records = result.records
    transaction_ids = [each.transaction_id for each in records.transactions]
    document = {
        "accounts": sorted(records.accounts, key=lambda each: each.account_id),
        "categories": sorted(records.categories, key=lambda each: each.category_id),
        "transactions": sorted(
            records.transactions, key=lambda each: each.transaction_id
        ),
        "category_allocations": sorted(
            records.category_allocations, key=lambda each: each.allocation_id
        ),
        "monthly_balances": sorted(
            records.monthly_balances, key=lambda each: (each.account_id, each.month)
        ),
        "transaction_lineage": sorted(
            result.transaction_lineage(transaction_ids),
            key=lambda each: each.transaction_id,
        ),
        "classification_review_items": sorted(
            result.classification_review_items(),
            key=lambda each: each.review_item_id,
        ),
    }
    text = json.dumps(
        {name: [asdict(each) for each in rows] for name, rows in document.items()},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_value,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_value(value: object) -> str:
    """Write a value JSON has no type for: an exact amount, a date or a time."""
    if isinstance(value, Decimal):
        return canonical_amount(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    message = f"no canonical form for {type(value).__name__}"
    raise TypeError(message)
