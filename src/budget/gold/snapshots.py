# Copyright 2026 Therkel
"""Monthly balance snapshots: one row per account per month of its managed period.

The managed period runs from the month of the account's first booked
transaction to the latest published month: the month of the latest
`evidence_through` over every Gold account (`gold-contract.md`,
*MonthlyBalanceSnapshot*).
"""

from collections.abc import Iterable, Sequence
from decimal import Decimal

from budget.gold.coverage import BalanceEvidence
from budget.gold.models import (
    Coverage,
    GoldAccount,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)
from budget.gold.months import first_day, months_through
from budget.silver.models import AccountEvidence, EvidenceExport


def monthly_balances(
    accounts: Sequence[GoldAccount],
    transactions: Sequence[GoldTransaction],
    ranges: Sequence[AccountEvidence],
    exports: Sequence[EvidenceExport],
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
            _history(account.account_id, transactions), ranges, exports, latest
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
    exports: Sequence[EvidenceExport],
    latest: ReportingMonth,
) -> list[MonthlyBalanceSnapshot]:
    """Snapshot one account; with no booked transaction it has no managed period."""
    if not history:
        return []
    evidence = BalanceEvidence.of(history, ranges, exports)
    return [
        _snapshot(month, history, evidence)
        for month in months_through(evidence.opened, latest)
    ]


def _snapshot(
    month: ReportingMonth,
    history: Sequence[GoldTransaction],
    evidence: BalanceEvidence,
) -> MonthlyBalanceSnapshot:
    coverage = evidence.coverage(month)
    opening, closing = _balances(month, history, coverage)
    return MonthlyBalanceSnapshot(
        account_id=history[0].account_id,
        month=month,
        opening_balance=opening,
        closing_balance=closing,
        coverage=coverage,
        late_bookings_settled=evidence.late_bookings_settled(month),
    )


def _balances(
    month: ReportingMonth, history: Sequence[GoldTransaction], coverage: Coverage
) -> tuple[Decimal | None, Decimal | None]:
    """Return the month's bank-stated opening and closing balances, if known.

    A complete quiet month carries the last stated balance into both; a quiet
    month that is not complete has neither, and neither has a `no_data` month.
    """
    if coverage == "no_data":
        return None, None
    inside = [t for t in history if ReportingMonth.of(t.transaction_date) == month]
    if inside:
        first, last = inside[0], inside[-1]
        opening = (
            None if first.balance_after is None else first.balance_after - first.amount
        )
        return opening, last.balance_after
    if coverage != "complete":
        return None, None
    carried = next(
        (
            t.balance_after
            for t in reversed(history)
            if t.transaction_date < first_day(month) and t.balance_after is not None
        ),
        None,
    )
    return carried, carried
