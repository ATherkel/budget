# Copyright 2026 Therkel
"""The balance chain within one export (ADR-010)."""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from budget.silver.formats import ReadRecord, RecordError

if TYPE_CHECKING:
    from decimal import Decimal

MISSING_BALANCE = "missing-balance"
CHAIN_BREAK = "balance-chain-break"
# The errors a `balance-break` review item stands for, and *accept
# discrepancy* settles.
BALANCE_BREAK_CODES = frozenset((MISSING_BALANCE, CHAIN_BREAK))


def chain_errors(
    records: Iterable[ReadRecord | None],
) -> list[tuple[ReadRecord, RecordError]]:
    """Check each booked row's balance against the previous one's.

    `records` is the payload in order, with None for a record that could not
    be read. The first booked row is trusted as the opening balance. A break
    re-anchors the chain on the break's own stated balance, and a missing
    balance or an unreadable record leaves the next link unverified.
    """
    found: list[tuple[ReadRecord, RecordError]] = []
    previous: Decimal | None = None
    for record in records:
        if record is None:
            previous = None
            continue
        if record.booking_status != "booked":
            continue
        if record.balance is None:
            found.append((record, RecordError(MISSING_BALANCE, "no balance stated")))
        elif previous is not None and previous + record.amount != record.balance:
            error = RecordError(CHAIN_BREAK, "balance does not follow the previous")
            found.append((record, error))
        previous = record.balance
    return found
