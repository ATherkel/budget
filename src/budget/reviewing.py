# Copyright 2026 Therkel
"""The `review` application operation: the open Silver review items.

Review reads the profile's persisted Silver result and nothing else: no Bronze
store, no `accounts.toml`, and no writer lock. It returns the items a person
still has to settle, each with the import run that raised it when the result
records one, so a command can name every decision target. It also returns the
quarantined runs no open item shows, so a run quarantined by validation errors
alone is not silent.
"""

from dataclasses import dataclass
from typing import Final

from budget.profiles import Profile
from budget.silver import ImportRunResult, ReviewItem, SilverStore

# The kinds Silver raises, as `silver-layer.md` names them.
REVIEW_KINDS: Final = (
    "balance-break",
    "dropped-transaction",
    "export-disagreement",
)


@dataclass(frozen=True)
class OpenReview:
    """One open review item, with the run that raised it when one is known."""

    item: ReviewItem
    import_run_id: str | None


@dataclass(frozen=True)
class OpenReviews:
    """What `review` lists: open items, then quarantined runs none of them shows."""

    items: tuple[OpenReview, ...]
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
    return OpenReviews(items=items, runs=runs)


def _wanted(item: ReviewItem, *, kind: str | None, account: str | None) -> bool:
    """Whether an open review item passes the command's two filters."""
    return (
        item.resolved_by is None
        and (kind is None or item.kind == kind)
        and (account is None or item.account_id == account)
    )
