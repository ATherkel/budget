# Copyright 2026 Therkel
"""Monthly balance snapshots: one row per account per month of its managed period.

The managed period runs from the month of the account's first booked
transaction to the latest published month: the month of the latest
`evidence_through` over every Gold account (`gold-contract.md`,
*MonthlyBalanceSnapshot*).
"""

from collections.abc import Iterable, Sequence

from budget.gold.coverage import BalanceEvidence
from budget.gold.models import (
    GoldAccount,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from budget.gold.months import months_through
from budget.silver.models import AccountEvidence


def monthly_balances(
    accounts: Sequence[GoldAccount],
    transactions: Sequence[GoldTransaction],
    ranges: Sequence[AccountEvidence],
) -> tuple[MonthlyBalanceSnapshot, ...]:
    """Snapshot every account for every month of its managed period."""
    latest = max(
        (ReportingMonth.of(a.evidence_through) for a in accounts if a.evidence_through),
        default=None,
    )
    if latest is None:
        return ()
    return tuple(
        snapshot
        for account in accounts
        for snapshot in _account_balances(
            _history(account.account_id, transactions), ranges, latest
        )
    )


def _history(
    account_id: str, transactions: Iterable[GoldTransaction]
) -> list[GoldTransaction]:
    return sorted(
        (t for t in transactions if t.account_id == account_id),
        key=lambda t: t.account_sequence,
    )


def _account_balances(
    history: Sequence[GoldTransaction],
    ranges: Sequence[AccountEvidence],
    latest: ReportingMonth,
) -> list[MonthlyBalanceSnapshot]:
    """Snapshot one account; with no booked transaction it has no managed period."""
    if not history:
        return []
    evidence = BalanceEvidence.of(history, ranges)
    return [
        MonthlyBalanceSnapshot(
            account_id=history[0].account_id,
            month=month,
            opening_balance=None,
            closing_balance=None,
            coverage=evidence.coverage(month),
            late_bookings_settled=False,
        )
        for month in months_through(evidence.opened, latest)
    ]
