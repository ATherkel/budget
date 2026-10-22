# Copyright 2026 Therkel
"""Transfer matching: pair claimed legs that cancel across two Gold accounts.

`classification.md` (*Transfer Matching*) and ADR-012 set the policy: a pair
needs a rule's transfer claim on at least one leg, and an unpaired claim stays
`unknown` with a reason a person can act on.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from budget.gold.models import GoldTransaction

type UnmatchedReason = Literal["counterpart-may-not-be-imported", "no-candidate"]

# The transfer matching policy's maximum date gap between two legs.
MAX_DATE_GAP = timedelta(days=3)


@dataclass(frozen=True)
class Matching:
    """What transfer matching decided for the claimed legs."""

    # Each unpaired claimed leg's transaction_id, and why it found no pair.
    unmatched: Mapping[str, UnmatchedReason]


def match_transfers(
    transactions: Sequence[GoldTransaction],
    claimed: Collection[str],
    account_ids: Collection[str],
) -> Matching:
    """Settle every leg in `claimed`, the transaction_ids a rule claims.

    `account_ids` names every Gold account, including those with no
    transactions, which may be waiting for their first import.
    """
    latest: dict[str, date] = {}
    for transaction in transactions:
        account_id = transaction.account_id
        latest[account_id] = max(
            transaction.transaction_date,
            latest.get(account_id, transaction.transaction_date),
        )
    return Matching(
        unmatched={
            t.transaction_id: _unmatched_reason(t, latest, account_ids)
            for t in transactions
            if t.transaction_id in claimed
        }
    )


def _unmatched_reason(
    leg: GoldTransaction,
    latest: Mapping[str, date],
    account_ids: Collection[str],
) -> UnmatchedReason:
    """Hint that the other leg may arrive with an account's next import.

    Some other account with nothing booked on or after the window's end may
    simply not be imported that far yet; a quiet account looks the same.
    """
    window_end = leg.transaction_date + MAX_DATE_GAP
    waiting = any(
        account_id != leg.account_id
        and (account_id not in latest or latest[account_id] < window_end)
        for account_id in account_ids
    )
    return "counterpart-may-not-be-imported" if waiting else "no-candidate"
