# Copyright 2026 Therkel
"""Transfer matching: pair claimed legs that cancel across two Gold accounts.

`classification.md` (*Transfer Matching*) and ADR-012 set the policy: a pair
needs a rule's transfer claim on at least one leg, and an unpaired claim stays
`unknown` with a reason a person can act on.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal

from budget.gold.models import GoldTransaction, TransferBasis, TransferEvidence
from budget.hashing import hash_parts

if TYPE_CHECKING:
    from decimal import Decimal

type UnmatchedReason = Literal["counterpart-may-not-be-imported", "no-candidate"]

# The transfer matching policy's maximum date gap between two legs.
MAX_DATE_GAP = timedelta(days=3)


@dataclass(frozen=True)
class PairedLeg:
    """One leg of a pair: the group both legs share, and its evidence."""

    transfer_group_id: str
    evidence: TransferEvidence


@dataclass(frozen=True)
class AmbiguousSet:
    """A candidate set Gold will not guess at: every leg waits for review."""

    # In booked order: account, then account_sequence.
    transaction_ids: tuple[str, ...]
    claim_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class Matching:
    """What transfer matching decided, by transaction_id."""

    paired: Mapping[str, PairedLeg]
    # Each leg held in an ambiguous set, and that set.
    ambiguous: Mapping[str, AmbiguousSet]
    # Each unpaired claimed leg, and why it found no pair.
    unmatched: Mapping[str, UnmatchedReason]


def match_transfers(
    transactions: Sequence[GoldTransaction],
    claims: Mapping[str, tuple[str, ...]],
    closed_on: Mapping[str, date | None],
) -> Matching:
    """Pair the legs that cancel, in stages by date gap (*Stages*).

    `claims` maps each claimed leg's transaction_id to the rules claiming it.
    `closed_on` maps every Gold account to its closing date, if any. It
    includes accounts with no transactions, which may be waiting for their
    first import.
    """
    paired: dict[str, PairedLeg] = {}
    ambiguous: dict[str, AmbiguousSet] = {}
    for gap in range(MAX_DATE_GAP.days + 1):
        available = [
            t
            for t in transactions
            if t.transaction_id not in paired and t.transaction_id not in ambiguous
        ]
        for legs in _connected_sets(_candidates(available, claims, gap)):
            pairs = _settle(legs)
            if pairs is None:
                ambiguous.update(_hold(legs, claims))
            for out, into, basis in pairs or ():
                paired.update(_pair(out, into, claims, gap, basis))

    latest = _latest_dates(transactions)
    return Matching(
        paired=paired,
        ambiguous=ambiguous,
        unmatched={
            t.transaction_id: _unmatched_reason(t, latest, closed_on)
            for t in transactions
            if t.transaction_id in claims
            and t.transaction_id not in paired
            and t.transaction_id not in ambiguous
        },
    )


def _candidates(
    legs: Sequence[GoldTransaction],
    claims: Mapping[str, tuple[str, ...]],
    gap: int,
) -> list[tuple[GoldTransaction, GoldTransaction]]:
    """List the (outgoing, incoming) candidate pairs exactly `gap` days apart.

    Every candidate has a claimed leg, so only the claimed legs look for an
    opposite amount; the pairs keep the legs' order, outgoing leg first.
    """
    position = {t.transaction_id: i for i, t in enumerate(legs)}
    by_amount: defaultdict[Decimal, list[GoldTransaction]] = defaultdict(list)
    for leg in legs:
        by_amount[leg.amount].append(leg)
    found = {
        (position[out.transaction_id], position[into.transaction_id])
        for claimed in legs
        if claimed.transaction_id in claims and claimed.amount != 0
        for other in by_amount.get(-claimed.amount, ())
        for out, into in (_outgoing_first(claimed, other),)
        if into.account_id != out.account_id and _gap(out, into) == gap
    }
    return [(legs[out], legs[into]) for out, into in sorted(found)]


def _outgoing_first(
    leg: GoldTransaction, other: GoldTransaction
) -> tuple[GoldTransaction, GoldTransaction]:
    return (leg, other) if leg.amount < 0 else (other, leg)


def _connected_sets(
    candidates: Sequence[tuple[GoldTransaction, GoldTransaction]],
) -> list[list[GoldTransaction]]:
    """Group the candidates' legs into sets joined by any candidate pair."""
    set_of: dict[str, list[GoldTransaction]] = {}
    for out, into in candidates:
        joined = set_of.get(out.transaction_id, [out])
        other = set_of.get(into.transaction_id, [into])
        if other is not joined:
            joined.extend(leg for leg in other if leg not in joined)
        for leg in joined:
            set_of[leg.transaction_id] = joined
    unique = {id(legs): legs for legs in set_of.values()}
    return list(unique.values())


def _settle(
    legs: Sequence[GoldTransaction],
) -> list[tuple[GoldTransaction, GoldTransaction, TransferBasis]] | None:
    """Pair a set's legs where no guess is needed; `None` if one would be.

    A lone pair pairs. Repeated legs are interchangeable, so they pair in
    booked order and any leftover stays for a later stage (*Stages*).
    """
    outs = sorted((t for t in legs if t.amount < 0), key=_booked_order)
    ins = sorted((t for t in legs if t.amount > 0), key=_booked_order)
    if len(outs) == len(ins) == 1:
        return [
            (outs[0], ins[0], "same_day" if _gap(outs[0], ins[0]) == 0 else "date_gap")
        ]
    if _repeated(outs) and _repeated(ins):
        return [
            (out, into, "repeated_legs") for out, into in zip(outs, ins, strict=False)
        ]
    return None


def _hold(
    legs: Sequence[GoldTransaction], claims: Mapping[str, tuple[str, ...]]
) -> dict[str, AmbiguousSet]:
    """Hold every leg of an ambiguous set, which raises one item for them all."""
    ordered = sorted(legs, key=_booked_order)
    held = AmbiguousSet(
        transaction_ids=tuple(t.transaction_id for t in ordered),
        claim_rule_ids=_claim_rules(ordered, claims),
    )
    return {t.transaction_id: held for t in ordered}


def _claim_rules(
    legs: Sequence[GoldTransaction], claims: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Name every rule claiming any of the legs, once each, sorted."""
    return tuple(
        sorted({rule_id for t in legs for rule_id in claims.get(t.transaction_id, ())})
    )


def _booked_order(leg: GoldTransaction) -> tuple[str, int]:
    return (leg.account_id, leg.account_sequence)


def _repeated(legs: Sequence[GoldTransaction]) -> bool:
    """Say whether the legs are interchangeable: one account, date, amount, text."""
    return (
        len({(t.account_id, t.transaction_date, t.amount, t.description) for t in legs})
        == 1
    )


def _gap(out: GoldTransaction, into: GoldTransaction) -> int:
    return abs((into.transaction_date - out.transaction_date).days)


def _pair(
    out: GoldTransaction,
    into: GoldTransaction,
    claims: Mapping[str, tuple[str, ...]],
    gap: int,
    basis: TransferBasis,
) -> dict[str, PairedLeg]:
    """Join two legs in one group, each naming the other as its evidence."""
    group_id = hash_parts(sorted([out.transaction_id, into.transaction_id]))
    claim_rule_ids = _claim_rules((out, into), claims)
    return {
        leg.transaction_id: PairedLeg(
            group_id,
            TransferEvidence(
                basis=basis,
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
    closed_on: Mapping[str, date | None],
) -> UnmatchedReason:
    """Hint that the other leg may arrive with an account's next import.

    Some other account with nothing booked on or after the window's end may
    simply not be imported that far yet; a quiet account looks the same. An
    account closed before the window starts can hold no counterpart.
    """
    window_start = leg.transaction_date - MAX_DATE_GAP
    window_end = leg.transaction_date + MAX_DATE_GAP
    waiting = any(
        account_id != leg.account_id
        and (closed is None or closed >= window_start)
        and (account_id not in latest or latest[account_id] < window_end)
        for account_id, closed in closed_on.items()
    )
    return "counterpart-may-not-be-imported" if waiting else "no-candidate"
