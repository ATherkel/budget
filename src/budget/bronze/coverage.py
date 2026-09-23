# Copyright 2026 Therkel
"""Bank-independent safeguards for a declared ``covers_through``.

Nothing in this module knows a source format. It decides how far one import
run's evidence may honestly reach, whatever produced the payload.
"""

from datetime import date, timedelta
from typing import Literal


def covers_through_for(
    declared: date | None,
    exported_on: date,
    last_transaction_date: date | None,
    *,
    payload_readable: bool,
) -> tuple[date, Literal["declared", "exported_on"], bool]:
    """Resolve an import run's covers_through, and whether it must be refused.

    bronze-layer.md "Covers through": bound a declaration, require it where the
    fallback would be wrong, fall back otherwise. The fallback records the
    export date itself and is marked `exported_on`; silver-layer.md reads that
    pair as evidence through the day before it.
    """
    if declared is not None:
        refused = declared > exported_on or (
            last_transaction_date is not None and declared < last_transaction_date
        )
        return declared, "declared", refused

    if not payload_readable:
        # A payload Bronze cannot decode is neither bounded nor unbounded by the
        # declaration; the FormatFailure is the verdict, not a refusal.
        return exported_on, "exported_on", False

    claimed_through = exported_on - timedelta(days=1)
    if last_transaction_date is None:
        # The payload states no transactions, so nothing bounds the range.
        refused = True
    elif exported_on < last_transaction_date:
        # The fallback does not even reach the payload's own last transaction.
        refused = True
    else:
        # Past the last transaction's reporting period the fallback would
        # manufacture the confirmed zeros this field exists to prevent. Inside
        # that period it is only the quiet tail of an ordinary export.
        refused = (claimed_through.year, claimed_through.month) > (
            last_transaction_date.year,
            last_transaction_date.month,
        )
    return exported_on, "exported_on", refused
