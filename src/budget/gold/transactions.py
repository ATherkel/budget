# Copyright 2026 Therkel
"""Gold transactions: Silver's booked transactions in each account's order.

Pending and cancelled rows stay Silver provenance (Gold contract, invariant 2).
"""

from collections.abc import Iterable, Sequence
from itertools import groupby

from budget.gold.models import GoldTransaction
from budget.silver.models import Transaction


def gold_transactions(silver: Iterable[Transaction]) -> tuple[GoldTransaction, ...]:
    """Order each account's transactions by date, then by Silver's day_sequence."""
    ordered = sorted(
        (t for t in silver if t.booking_status == "booked"),
        key=lambda t: (t.account_id, t.transaction_date, t.day_sequence),
    )
    return tuple(
        gold
        for _, history in groupby(ordered, key=lambda t: t.account_id)
        for gold in _account_history(list(history))
    )


def _account_history(history: Sequence[Transaction]) -> list[GoldTransaction]:
    """Publish one account's transactions, already in their booked order."""
    return [
        GoldTransaction(
            transaction_id=t.transaction_id,
            account_id=t.account_id,
            transaction_date=t.transaction_date,
            account_sequence=sequence,
            amount=t.amount,
            description=t.description,
            transaction_type="unknown",
            transfer_group_id=None,
            balance_after=t.balance,
            balance_check="opening",
        )
        for sequence, t in enumerate(history, start=1)
    ]
