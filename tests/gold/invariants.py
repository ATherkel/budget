# Copyright 2026 Therkel
"""Gold contract invariants 10 and 12, checked over any `GoldRepository`.

`gold-contract.md`, *Invariants*:

10. Per account, `account_sequence` runs 1, 2, 3, ... without gaps, and
    `transaction_date` never decreases as `account_sequence` increases.
12. `MonthlyBalanceSnapshot` has exactly one row per account per month of the
    managed period. When a row's `coverage` is `complete`,
    `opening_balance + sum(amounts in the month) == closing_balance`.

The check reads only through `GoldRepository`, so a store-backed repository is
checked unchanged. It derives each managed period from the contract's rule, with
its own month arithmetic, rather than from the build's snapshot code.
"""

from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import override

from budget.gold import (
    GoldAccount,
    GoldRepository,
    GoldTransaction,
    MonthlyBalanceSnapshot,
    ReportingMonth,
)

_EARLIEST_MONTH = ReportingMonth(1, 1)
_LATEST_MONTH = ReportingMonth(9999, 12)


@dataclass(frozen=True)
class Violation:
    """One broken invariant, on one account and, where relevant, one month."""

    invariant: int
    account_id: str
    month: ReportingMonth | None
    problem: str

    @override
    def __str__(self) -> str:
        """Name the invariant, the account, the month if any, and the problem."""
        where = self.account_id
        if self.month is not None:
            where += f" {self.month.year:04d}-{self.month.month:02d}"
        return f"invariant {self.invariant}, {where}: {self.problem}"


def assert_contract_invariants(repository: GoldRepository) -> None:
    """Fail once, listing every violation of invariants 10 and 12."""
    violations = contract_violations(repository)
    if violations:
        listed = "\n".join(f"  {violation}" for violation in violations)
        message = f"the Gold result breaks the contract:\n{listed}"
        raise AssertionError(message)


def contract_violations(repository: GoldRepository) -> list[Violation]:
    """Return every violation of invariants 10 and 12 in `repository`.

    Violations come per account, in the repository's account order: invariant
    10 first, then invariant 12's months, then its balances, months in order.
    """
    accounts = repository.accounts()
    latest_published = _latest_published_month(accounts)
    violations: list[Violation] = []
    for account in accounts:
        transactions = repository.transactions(
            start_date=date.min,
            end_date=date.max,
            account_ids=[account.account_id],
        )
        rows = repository.monthly_balances(
            start_month=_EARLIEST_MONTH,
            end_month=_LATEST_MONTH,
            account_ids=[account.account_id],
        )
        managed = _managed_period(account, transactions, latest_published)
        violations.extend(_sequence_violations(account.account_id, transactions))
        violations.extend(_month_violations(account.account_id, managed, rows))
        violations.extend(_balance_violations(account.account_id, transactions, rows))
    return violations


def _sequence_violations(
    account_id: str, transactions: Sequence[GoldTransaction]
) -> list[Violation]:
    """Invariant 10: `account_sequence` is exactly 1..n; dates never go back."""
    in_sequence = sorted(transactions, key=lambda t: t.account_sequence)
    counts = Counter(t.account_sequence for t in in_sequence)
    distinct = sorted(counts)
    problems = []
    if distinct and distinct[0] != 1:
        problems.append(f"account_sequence starts at {distinct[0]}, not 1")
    problems.extend(
        f"account_sequence {sequence} appears {count} times"
        for sequence, count in counts.items()
        if count > 1
    )
    problems.extend(
        f"account_sequence skips from {a} to {b}"
        for a, b in pairwise(distinct)
        if b != a + 1
    )
    problems.extend(
        f"transaction_date goes back from {earlier.transaction_date} "
        f"to {later.transaction_date} at account_sequence {later.account_sequence}"
        for earlier, later in pairwise(in_sequence)
        if later.transaction_date < earlier.transaction_date
    )
    return [Violation(10, account_id, None, problem) for problem in problems]


def _latest_published_month(accounts: Sequence[GoldAccount]) -> ReportingMonth | None:
    """The month of the latest `evidence_through` over every account."""
    stated = [a.evidence_through for a in accounts if a.evidence_through is not None]
    return ReportingMonth.of(max(stated)) if stated else None


def _managed_period(
    account: GoldAccount,
    transactions: Sequence[GoldTransaction],
    latest_published: ReportingMonth | None,
) -> list[ReportingMonth]:
    """From the first booked month to the latest published month or `closed_on`."""
    if not transactions or latest_published is None:
        return []
    first = ReportingMonth.of(min(t.transaction_date for t in transactions))
    last = latest_published
    if account.closed_on is not None:
        last = min(last, ReportingMonth.of(account.closed_on))
    return list(_months(first, last))


def _months(first: ReportingMonth, last: ReportingMonth) -> Iterator[ReportingMonth]:
    """Every month from `first` through `last`."""
    index, last_index = _month_index(first), _month_index(last)
    while index <= last_index:
        yield ReportingMonth(index // 12, index % 12 + 1)
        index += 1


def _month_index(month: ReportingMonth) -> int:
    return month.year * 12 + month.month - 1


def _month_violations(
    account_id: str,
    managed: Sequence[ReportingMonth],
    rows: Sequence[MonthlyBalanceSnapshot],
) -> list[Violation]:
    """Invariant 12: exactly one row per month of the managed period."""
    counts = Counter(row.month for row in rows)
    violations = []
    for month in sorted(set(managed) | set(counts)):
        if month not in managed:
            problem = "row is outside the managed period"
        elif counts[month] == 0:
            problem = "month of the managed period has no row"
        elif counts[month] > 1:
            problem = f"month has {counts[month]} rows"
        else:
            continue
        violations.append(Violation(12, account_id, month, problem))
    return violations


def _balance_violations(
    account_id: str,
    transactions: Sequence[GoldTransaction],
    rows: Sequence[MonthlyBalanceSnapshot],
) -> list[Violation]:
    """Invariant 12: a `complete` row states both balances, and they add up."""
    amounts: defaultdict[ReportingMonth, Decimal] = defaultdict(Decimal)
    for transaction in transactions:
        amounts[ReportingMonth.of(transaction.transaction_date)] += transaction.amount
    violations = []
    for row in sorted(rows, key=lambda r: r.month):
        if row.coverage != "complete":
            continue
        violations.extend(
            Violation(12, account_id, row.month, problem)
            for problem in _balance_problems(row, amounts[row.month])
        )
    return violations


def _balance_problems(row: MonthlyBalanceSnapshot, amounts: Decimal) -> list[str]:
    """Why a `complete` row's balances fail, checking for nulls before the sum."""
    opening, closing = row.opening_balance, row.closing_balance
    if opening is None or closing is None:
        return [
            f"complete row has no {name}"
            for name, balance in (
                ("opening_balance", opening),
                ("closing_balance", closing),
            )
            if balance is None
        ]
    if opening + amounts == closing:
        return []
    added = f"opening_balance {opening} + amounts {amounts}"
    return [f"{added} != closing_balance {closing}"]
