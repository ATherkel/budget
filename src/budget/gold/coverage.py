# Copyright 2026 Therkel
"""What one account's evidence says about a month (`gold-layer.md`, *Coverage*).

That is the month's coverage, and whether its late bookings are settled.

A link joins two consecutive booked transactions and spans both their dates.
It is verified when both balances exist and the later balance is the earlier
plus the later amount. Bridging a missing balance for `balance_check` does not
verify either link beside it.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import pairwise
from typing import Self

from budget.gold.models import Coverage, GoldTransaction, ReportingMonth
from budget.gold.months import first_day, last_day
from budget.silver.models import AccountEvidence, EvidenceExport


@dataclass(frozen=True)
class _Link:
    """Two consecutive transactions, from the earlier's date to the later's."""

    starts: date
    ends: date
    verified: bool


def _links(history: Sequence[GoldTransaction]) -> tuple[_Link, ...]:
    return tuple(
        _Link(
            starts=earlier.transaction_date,
            ends=later.transaction_date,
            verified=earlier.balance_after is not None
            and later.balance_after is not None
            and later.balance_after == earlier.balance_after + later.amount,
        )
        for earlier, later in pairwise(history)
    )


@dataclass(frozen=True)
class BalanceEvidence:
    """One account's balance evidence: its ranges and its transaction links.

    `late_booking_window` is how long after a month ends an export must be
    produced to show the month's late bookings.
    """

    opened: ReportingMonth
    ranges: tuple[AccountEvidence, ...]
    exports: tuple[EvidenceExport, ...]
    links: tuple[_Link, ...]
    late_booking_window: timedelta

    @classmethod
    def of(
        cls,
        history: Sequence[GoldTransaction],
        ranges: Iterable[AccountEvidence],
        exports: Iterable[EvidenceExport],
        late_booking_window: timedelta,
    ) -> Self:
        """Gather the evidence of the account `history` belongs to, in booked order."""
        account_id = history[0].account_id
        return cls(
            opened=ReportingMonth.of(history[0].transaction_date),
            ranges=tuple(r for r in ranges if r.account_id == account_id),
            exports=tuple(e for e in exports if e.account_id == account_id),
            links=_links(history),
            late_booking_window=late_booking_window,
        )

    def coverage(self, month: ReportingMonth) -> Coverage:
        """Return the month's coverage: `complete`, `partial` or `no_data`."""
        first, last = first_day(month), last_day(month)
        if not any(
            r.covers_from <= last and first <= r.covers_through for r in self.ranges
        ):
            return "no_data"
        # The first transaction opens the chain, so no link verifies the
        # balance the account entered its first managed month with.
        if month == self.opened:
            return "partial"
        whole = any(
            r.covers_from <= first and last <= r.covers_through for r in self.ranges
        )
        broken = any(
            not link.verified and link.starts <= last and first <= link.ends
            for link in self.links
        )
        return "complete" if whole and not broken else "partial"

    def late_bookings_settled(self, month: ReportingMonth) -> bool:
        """Whether a counted export shows the month's late bookings.

        It must be produced at least `late_booking_window` after the month's last
        day, and its declared range must include that day.
        """
        last = last_day(month)
        return any(
            e.exported_on >= last + self.late_booking_window
            and e.covers_from <= last <= e.covers_through
            for e in self.exports
        )
