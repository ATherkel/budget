# Copyright 2026 Therkel
"""The production household reports over a real test-profile Gold store."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from budget.analytics import HouseholdReports, NothingPublishedError, ReportPublication
from budget.gold import GoldPublication, GoldResult
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.gold.test_store import CONFIGURATION, RECIPE
from tests.gold.worked_example import PUBLICATION, RECORDS


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    """Create and migrate the ephemeral Gold store this module tests."""
    migrated = make_test_profile(tmp_path)
    migrate_gold(migrated)
    return migrated


@pytest.fixture
def gold_store(profile: Profile) -> Iterator[GoldStore]:
    """Yield the one real Gold store used by a test."""
    with GoldStore(profile) as store:
        yield store


def _publish(store: GoldStore, publication_id: int) -> GoldPublication:
    publication = replace(PUBLICATION, publication_id=publication_id)
    store.publish(GoldResult(publication, RECORDS), RECIPE, CONFIGURATION)
    return publication


def test_current_publication_returns_the_current_build(gold_store: GoldStore) -> None:
    publication = _publish(gold_store, 1)

    assert HouseholdReports(gold_store).current_publication() == ReportPublication(
        publication_id=1,
        kind="pipeline",
        label=None,
        known_at=publication.known_at,
        is_current=True,
    )


def test_before_the_first_build_nothing_is_published(gold_store: GoldStore) -> None:
    reports = HouseholdReports(gold_store)

    with pytest.raises(NothingPublishedError):
        reports.current_publication()
    assert gold_store.current() is None


def test_selection_options_open_the_requested_superseded_publication(
    gold_store: GoldStore,
) -> None:
    old_records = replace(
        RECORDS,
        accounts=tuple(
            replace(account, display_name=f"Old {account.display_name}")
            for account in RECORDS.accounts
        ),
    )
    old = replace(PUBLICATION, publication_id=1)
    gold_store.publish(GoldResult(old, old_records), RECIPE, CONFIGURATION)
    _publish(gold_store, 2)

    options = HouseholdReports(gold_store).selection_options(1, date(2026, 5, 14))

    assert (options.publication.publication_id, options.publication.is_current) == (
        1,
        False,
    )
    assert [account.display_name for account in options.accounts] == [
        "Old Joint current",
        "Old Joint savings",
    ]
