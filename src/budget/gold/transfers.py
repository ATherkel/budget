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

from budget.gold.models import GoldTransaction, TransferEvidence
from budget.hashing import hash_parts

type UnmatchedReason = Literal["counterpart-may-not-be-imported", "no-candidate"]

# The transfer matching policy's maximum date gap between two legs.
MAX_DATE_GAP = timedelta(days=3)


@dataclass(frozen=True)
class PairedLeg:
    """One leg of a pair: the group both legs share, and its evidence."""

    transfer_group_id: str
    evidence: TransferEvidence


@dataclass(frozen=True)
class Matching:
    """What transfer matching decided, by transaction_id."""

    paired: Mapping[str, PairedLeg]
    # Each unpaired claimed leg, and why it found no pair.
    unmatched: Mapping[str, UnmatchedReason]


def match_transfers(
    transactions: Sequence[GoldTransaction],
    claims: Mapping[str, tuple[str, ...]],
    account_ids: Collection[str],
) -> Matching:
    """Pair the legs that cancel, in stages by date gap (*Stages*).

    `claims` maps each claimed leg's transaction_id to the rules claiming it.
    `account_ids` names every Gold account, including those with no
    transactions, which may be waiting for their first import.
    """
    paired: dict[str, PairedLeg] = {}
    for gap in range(MAX_DATE_GAP.days + 1):
        available = [t for t in transactions if t.transaction_id not in paired]
        for out, into in _lone_pairs(_candidates(available, claims, gap)):
            paired.update(_pair(out, into, claims, gap))

    latest = _latest_dates(transactions)
    return Matching(
        paired=paired,
        unmatched={
            t.transaction_id: _unmatched_reason(t, latest, account_ids)
            for t in transactions
            if t.transaction_id in claims and t.transaction_id not in paired
        },
    )


def _candidates(
    legs: Sequence[GoldTransaction],
    claims: Mapping[str, tuple[str, ...]],
    gap: int,
) -> list[tuple[GoldTransaction, GoldTransaction]]:
    """List the (outgoing, incoming) candidate pairs exactly `gap` days apart."""
    return [
        (out, into)
        for out in legs
        if out.amount < 0
        for into in legs
        if into.amount == -out.amount
        and into.account_id != out.account_id
        and abs((into.transaction_date - out.transaction_date).days) == gap
        and (out.transaction_id in claims or into.transaction_id in claims)
    ]


def _lone_pairs(
    candidates: Sequence[tuple[GoldTransaction, GoldTransaction]],
) -> list[tuple[GoldTransaction, GoldTransaction]]:
    """Keep the candidates whose legs are candidates for nothing else."""
    uses: dict[str, int] = {}
    for out, into in candidates:
        for leg in (out, into):
            uses[leg.transaction_id] = uses.get(leg.transaction_id, 0) + 1
    return [
        (out, into)
        for out, into in candidates
        if uses[out.transaction_id] == uses[into.transaction_id] == 1
    ]


def _pair(
    out: GoldTransaction,
    into: GoldTransaction,
    claims: Mapping[str, tuple[str, ...]],
    gap: int,
) -> dict[str, PairedLeg]:
    """Join two legs in one group, each naming the other as its evidence."""
    group_id = hash_parts(sorted([out.transaction_id, into.transaction_id]))
    claim_rule_ids = tuple(
        sorted(
            {*claims.get(out.transaction_id, ()), *claims.get(into.transaction_id, ())}
        )
    )
    return {
        leg.transaction_id: PairedLeg(
            group_id,
            TransferEvidence(
                basis="same_day" if gap == 0 else "date_gap",
                counterpart_account_id=other.account_id,
                counterpart_transaction_id=other.transaction_id,
                date_gap_days=gap,
                claim_rule_ids=claim_rule_ids,
            ),
        )
        for leg, other in ((out, into), (into, out))
    }


def _latest_dates(transactions: Sequence[GoldTransaction]) -> dict[str, date]:
    """Find each account's latest transaction date."""
    latest: dict[str, date] = {}
    for transaction in transactions:
        account_id = transaction.account_id
        latest[account_id] = max(
            transaction.transaction_date,
            latest.get(account_id, transaction.transaction_date),
        )
    return latest


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
