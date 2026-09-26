# Copyright 2026 Therkel
"""Whether each import run is admitted, and the review items it raises."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date

from budget.silver.balances import BALANCE_BREAK_CODES
from budget.silver.decisions import (
    AcceptDiscrepancy,
    SameTransaction,
    SilverDecision,
    VoidImportRun,
    Withdrawn,
)
from budget.silver.identity import review_item_id
from budget.silver.merge import Ledger
from budget.silver.models import ReviewItem
from budget.silver.reading import Key, ReadRun


@dataclass(frozen=True)
class Decisions:
    """The effective Silver decisions, indexed by what they target."""

    voided: frozenset[str]  # import_run_id
    accepted: dict[str, str]  # import_run_id -> decision_id
    withdrawn: dict[str, str]  # transaction_id -> decision_id
    same: dict[tuple[str, str], SameTransaction]  # (transaction_id, payload_id)

    @classmethod
    def of(cls, decisions: Sequence[SilverDecision]) -> "Decisions":
        """Index `decisions` by what they target."""
        return cls(
            voided=frozenset(
                d.import_run_id for d in decisions if isinstance(d, VoidImportRun)
            ),
            accepted={
                d.import_run_id: d.decision_id
                for d in decisions
                if isinstance(d, AcceptDiscrepancy)
            },
            withdrawn={
                d.transaction_id: d.decision_id
                for d in decisions
                if isinstance(d, Withdrawn)
            },
            same={
                (d.transaction_id, d.payload_id): d
                for d in decisions
                if isinstance(d, SameTransaction)
            },
        )

    def settling_drop(self, transaction_id: str, payload_id: str) -> str | None:
        """Name the decision that settles dropping `transaction_id` here."""
        same = self.same.get((transaction_id, payload_id))
        if same is not None:
            return same.decision_id
        return self.withdrawn.get(transaction_id)


@dataclass(frozen=True)
class Admission:
    """A run with the review items it raised and whether it is admitted."""

    each: ReadRun
    review_items: tuple[ReviewItem, ...]
    admitted: bool


def judge(each: ReadRun, decisions: Decisions) -> Admission:
    """Raise the run's own review items and admit it if they settle its errors."""
    if not each.break_dates:
        return Admission(each=each, review_items=(), admitted=not each.errors)
    resolved_by = decisions.accepted.get(each.run.import_run_id)
    item = ReviewItem(
        review_item_id=review_item_id("balance-break", each.run.import_run_id),
        kind="balance-break",
        account_id=each.account_id,
        date_from=min(each.break_dates),
        date_to=max(each.break_dates),
        payload_ids=(each.run.payload_id,),
        resolved_by=resolved_by,
    )
    settled = BALANCE_BREAK_CODES if resolved_by is not None else frozenset()
    return Admission(
        each=each,
        review_items=(item,),
        admitted=all(error.code in settled for error in each.errors),
    )


@dataclass(frozen=True)
class _Drop:
    """One transaction a run drops, its review item and any remap."""

    key: Key
    occurrence: int
    item: ReviewItem
    same: SameTransaction | None


def admit(judged: Admission, ledger: Ledger, decisions: Decisions) -> Admission:
    """Admit a valid run whose merge verifies, or whose drops are all decided."""
    if not judged.admitted:
        return judged
    each = judged.each
    verdict = ledger.verdict(each)
    drops = [_drop(each, ledger, key, k, decisions) for key, k in verdict.dropped]
    items = (*judged.review_items, *(drop.item for drop in drops))
    if verdict.disagreements:
        items = (*items, _disagreement(each, verdict.disagreements))
    if verdict.disagreements or any(drop.item.resolved_by is None for drop in drops):
        return Admission(each=each, review_items=items, admitted=False)
    admitted = _remapped(each, drops)
    ledger.admit(
        admitted,
        withdrawn=[(drop.key, drop.occurrence) for drop in drops if drop.same is None],
    )
    return Admission(each=admitted, review_items=items, admitted=True)


def _drop(
    each: ReadRun, ledger: Ledger, key: Key, k: int, decisions: Decisions
) -> _Drop:
    """Raise the item for one dropped transaction, with its settlement."""
    transaction_id = ledger.identify(key, k)
    payload_id = each.run.payload_id
    item = ReviewItem(
        review_item_id=review_item_id(
            "dropped-transactions", each.run.import_run_id, transaction_id
        ),
        kind="dropped-transactions",
        account_id=each.account_id,
        date_from=key[0],
        date_to=key[0],
        payload_ids=(payload_id, ledger.selected[key[0]].run.payload_id),
        resolved_by=decisions.settling_drop(transaction_id, payload_id),
        transaction_id=transaction_id,
    )
    same = decisions.same.get((transaction_id, payload_id))
    return _Drop(key=key, occurrence=k, item=item, same=same)


def _remapped(each: ReadRun, drops: Iterable[_Drop]) -> ReadRun:
    """Make each record a *same transaction* decision names show its target."""
    targets = {
        drop.same.record_ordinal: (drop.key, drop.occurrence)
        for drop in drops
        if drop.same is not None
    }
    return replace(
        each,
        booked=tuple(
            replace(row, key=target[0], occurrence=target[1])
            if (target := targets.get(row.record.record.record_ordinal))
            else row
            for row in each.booked
        ),
    )


def _disagreement(
    each: ReadRun, disagreements: Sequence[tuple[date, str]]
) -> ReviewItem:
    """Raise the item for balances unexplained by every added and dropped amount."""
    days = [day for day, _ in disagreements]
    compared = sorted({payload_id for _, payload_id in disagreements})
    return ReviewItem(
        review_item_id=review_item_id("export-disagreement", each.run.import_run_id),
        kind="export-disagreement",
        account_id=each.account_id,
        date_from=min(days),
        date_to=max(days),
        payload_ids=(each.run.payload_id, *compared),
        resolved_by=None,
    )
