# Copyright 2026 Therkel
"""The `review` application operation: open Silver and Gold review items.

Review reads the persisted Silver result and the current retained Gold
publication: no Bronze store, no `accounts.toml`, and no writer lock. Gold's
items and identifier lists are materialized in one SQLite snapshot, so a
concurrent publish or retention cleanup cannot mix publications.
"""

from dataclasses import dataclass
from typing import Final

from budget.gold import ClassificationReviewItem
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.silver import ImportRunResult, ReviewItem, SilverStore

# The kinds Silver raises, as `silver-layer.md` names them.
SILVER_REVIEW_KINDS: Final = (
    "balance-break",
    "dropped-transaction",
    "export-disagreement",
)
# The kinds Gold derives afresh for each publication (classification.md).
GOLD_REVIEW_KINDS: Final = (
    "unclassified",
    "rule-conflict",
    "sign-mismatch",
    "ambiguous-transfer",
    "unmatched-transfer",
    "decision-not-applicable",
)
REVIEW_KINDS: Final = (*SILVER_REVIEW_KINDS, *GOLD_REVIEW_KINDS)


@dataclass(frozen=True)
class OpenReview:
    """One open review item, with the run that raised it when one is known."""

    item: ReviewItem
    import_run_id: str | None


@dataclass(frozen=True)
class OpenGoldReview:
    """One classification question from the current retained publication."""

    item: ClassificationReviewItem
    publication_id: int


@dataclass(frozen=True)
class OpenReviews:
    """What `review` lists: open items, then quarantined runs none of them shows."""

    items: tuple[OpenReview, ...]
    gold_items: tuple[OpenGoldReview, ...]
    runs: tuple[ImportRunResult, ...]


def open_reviews(
    profile: Profile,
    *,
    kind: str | None = None,
    account: str | None = None,
) -> OpenReviews:
    """Return the filtered open review items and the quarantined runs left over.

    A run with an open review item is shown through that item, whatever filter
    hides it. A run has no kind, so `kind` leaves the remaining runs out.
    """
    with SilverStore(profile, read_only=True) as store:
        result = store.read()
    raised_by = {
        item_id: run.import_run_id
        for run in result.import_run_results
        for item_id in run.review_item_ids
    }
    open_ids = {
        item.review_item_id for item in result.review_items if item.resolved_by is None
    }
    items = tuple(
        OpenReview(item=item, import_run_id=raised_by.get(item.review_item_id))
        for item in result.review_items
        if _wanted(item, kind=kind, account=account)
    )
    runs = tuple(
        run
        for run in result.import_run_results
        if kind is None
        and run.status == "quarantined"
        and (account is None or run.account_id == account)
        and open_ids.isdisjoint(run.review_item_ids)
    )
    return OpenReviews(
        items=items,
        gold_items=_gold_reviews(profile, kind=kind, account=account),
        runs=runs,
    )


def _gold_reviews(
    profile: Profile,
    *,
    kind: str | None,
    account: str | None,
) -> tuple[OpenGoldReview, ...]:
    """Read the current Gold publication, or no Gold items when none exists."""
    if not profile.gold_store.exists():
        return ()
    with GoldStore(profile, read_only=True) as store:
        published = store.classification_reviews(kind=kind, account=account)
    if published is None:
        return ()
    return tuple(
        OpenGoldReview(item=item, publication_id=published.publication_id)
        for item in published.items
    )


def _wanted(item: ReviewItem, *, kind: str | None, account: str | None) -> bool:
    """Whether an open review item passes the command's two filters."""
    return (
        item.resolved_by is None
        and (kind is None or item.kind == kind)
        and (account is None or item.account_id == account)
    )
