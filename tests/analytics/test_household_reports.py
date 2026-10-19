# Copyright 2026 Therkel
"""`HouseholdReports`: the report interface of `report-contract.md` over `gold.db`.

Every store is the test profile's, in a temporary folder, holding the
synthetic worked example published under one or more ids.
"""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from budget.analytics import HouseholdReports, ReportPublication
from budget.gold import GoldResult
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.gold.test_store import CONFIGURATION, RECIPE
from tests.gold.worked_example import PUBLICATION, RECORDS

SECOND_BUILD_AT = datetime(2026, 5, 16, 7, 30, tzinfo=UTC)


def publish(store: GoldStore, publication_id: int, known_at: datetime) -> None:
    """Publish the worked example as `publication_id`, known at `known_at`.

    It was built an hour later, so a report that shows `built_at` is caught.
    """
    published = replace(
        PUBLICATION,
        publication_id=publication_id,
        known_at=known_at,
        built_at=known_at + timedelta(hours=1),
    )
    store.publish(GoldResult(published, RECORDS), RECIPE, CONFIGURATION)


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    migrated = make_test_profile(tmp_path)
    migrate_gold(migrated)
    return migrated


@pytest.fixture
def store(profile: Profile) -> Iterator[GoldStore]:
    with GoldStore(profile) as opened:
        yield opened


def test_the_current_publication_is_the_one_gold_marks_current(
    store: GoldStore,
) -> None:
    publish(store, 1, PUBLICATION.known_at)
    publish(store, 2, SECOND_BUILD_AT)

    assert HouseholdReports(store).current_publication() == ReportPublication(
        publication_id=2,
        kind="pipeline",
        label=None,
        known_at=SECOND_BUILD_AT,
        is_current=True,
    )
