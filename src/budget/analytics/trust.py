# Copyright 2026 Therkel
"""Coverage and the provisional label, as `report-contract.md` defines them.

Analytics reads coverage from Gold's snapshot rows and never recomputes it.
An account's rows span exactly its managed period, so they also tell which
months lie outside its reported history.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from budget.analytics.reports import (
    AccountMonth,
    AccountMonthCoverage,
    Provisional,
    ProvisionalReason,
    ReportCoverage,
)
from budget.gold import Coverage, GoldAccount, MonthlyBalanceSnapshot, ReportingMonth

type AccountMonthState = Literal["complete", "partial", "no_data", "outside_history"]


@dataclass(frozen=True)
class _Evidence:
    """What Gold says about one selected account in the selected month."""

    account: GoldAccount
    state: AccountMonthState
    unsettled: bool


def _evidence(
    account: GoldAccount,
    rows: Sequence[MonthlyBalanceSnapshot],
    month: ReportingMonth,
) -> _Evidence:
    """Judge one account-month from every snapshot row the account has."""
    row = next((row for row in rows if row.month == month), None)
    if row is not None:
        return _Evidence(account, row.coverage, unsettled=not row.late_bookings_settled)
    if not rows:
        # No managed period yet: never imported, or no booked transaction. The
        # provisional rule exempts it.
        return _Evidence(account, "no_data", unsettled=False)
    closed = account.closed_on
    if month < min(row.month for row in rows) or (
        closed is not None and month > ReportingMonth.of(closed)
    ):
        return _Evidence(account, "outside_history", unsettled=False)
    # Inside the managed period but without a row: after the latest published
    # month, which no export has settled yet.
    return _Evidence(account, "no_data", unsettled=True)


def combined_status(states: Collection[AccountMonthState]) -> Coverage:
    """Return the report's coverage from its selected account-months' states.

    `report-contract.md`, *Coverage*: the contributing account-months are the
    ones not `outside_history`; the status is `complete` when every one is
    `complete`, `no_data` when none has evidence (including when none
    contributes), and `partial` otherwise.
    """
    contributing = [state for state in states if state != "outside_history"]
    if all(state == "no_data" for state in contributing):
        return "no_data"
    if all(state == "complete" for state in contributing):
        return "complete"
    return "partial"


@dataclass(frozen=True)
class Trust:
    """A report's coverage and provisional label."""

    coverage: ReportCoverage
    provisional: Provisional | None


def trust(
    accounts: Sequence[GoldAccount],
    rows: Sequence[MonthlyBalanceSnapshot],
    month: ReportingMonth,
    reference_date: date,
) -> Trust:
    """Judge `month` for `accounts` from all their rows, on `reference_date`."""
    evidence = [
        _evidence(
            account, [r for r in rows if r.account_id == account.account_id], month
        )
        for account in sorted(accounts, key=lambda account: account.account_id)
    ]
    coverage = ReportCoverage(
        status=combined_status([e.state for e in evidence]),
        account_months=tuple(
            AccountMonthCoverage(
                e.account.account_id, e.account.display_name, month, e.state
            )
            for e in evidence
            if e.state != "complete"
        ),
    )
    unsettled = tuple(
        AccountMonth(e.account.account_id, e.account.display_name, month)
        for e in evidence
        if e.unsettled
    )
    reasons: set[ProvisionalReason] = set()
    if month == ReportingMonth.of(reference_date):
        reasons.add("current_month")
    if unsettled:
        reasons.add("late_bookings_unsettled")
    return Trust(
        coverage=coverage,
        provisional=Provisional(frozenset(reasons), unsettled) if reasons else None,
    )
