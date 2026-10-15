# Copyright 2026 Therkel
"""`GoldStore`: the publications `gold.db` holds, served as `GoldPublications`.

Every store is the test profile's, in a temporary folder, created by
`migrate_gold`. All data is the synthetic worked example.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile


@pytest.fixture
def profile(tmp_path: Path) -> Profile:
    migrated = make_test_profile(tmp_path)
    migrate_gold(migrated)
    return migrated


@pytest.fixture
def store(profile: Profile) -> Iterator[GoldStore]:
    with GoldStore(profile) as opened:
        yield opened


def test_a_new_store_has_no_current_publication(tmp_path: Path) -> None:
    profile = make_test_profile(tmp_path)

    migrate_gold(profile)
    with GoldStore(profile) as store:
        current = store.current()
        available = list(store.available())

    assert current is None
    assert available == []
