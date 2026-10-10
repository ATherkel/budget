# Copyright 2026 Therkel
"""The balance chain, as `gold-layer.md` (*Balance Chain Evaluation*) defines it.

Gold keeps an anchor, the last known bank-stated balance, and the sum of the
amounts booked since it. Bridging a missing balance verifies the chain; it
never invents the missing value.
"""

from collections.abc import Iterable
from decimal import Decimal

from budget.gold.models import BalanceCheck


def balance_checks(
    history: Iterable[tuple[Decimal, Decimal | None]],
) -> list[BalanceCheck]:
    """Check each `(amount, balance_after)` of one account, in booked order."""
    anchor: Decimal | None = None
    since_anchor = Decimal(0)
    checks: list[BalanceCheck] = []
    for amount, balance_after in history:
        if balance_after is None:
            checks.append("missing_balance")
            since_anchor += amount
            continue
        if anchor is None:
            checks.append("opening")
        elif balance_after == anchor + since_anchor + amount:
            checks.append("consistent")
        else:
            checks.append("break")  # re-anchor, so one break does not cascade
        anchor, since_anchor = balance_after, Decimal(0)
    return checks
