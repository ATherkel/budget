# Copyright 2026 Therkel
"""`GoldStore`: the publications `gold.db` holds, served as `GoldPublications`.

Every store is the test profile's, in a temporary folder, created by
`migrate_gold`. All data is the synthetic worked example.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from budget.gold import GoldRepository, GoldResult
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.storage import migrate_gold
from budget.gold.store import GoldStore
from budget.inputs import ConfigurationSnapshot
from budget.profiles import Profile
from budget.profiles import test_profile as make_test_profile
from tests.gold.contract import GoldRepositoryContract
from tests.gold.worked_example import PUBLICATION, RECORDS
from tests.gold.worked_silver import REGISTRY, TAXONOMY

CONFIGURATION = ConfigurationSnapshot(accounts=REGISTRY, taxonomy=TAXONOMY, rules={})
RECIPE = Recipe(
    import_runs=frozenset(
        {
            RecipeImportRun("run-current", "a" * 64),
            RecipeImportRun("run-savings", "b" * 64),
        }
    ),
    configuration_fingerprint=CONFIGURATION.fingerprint,
    decision_log_position=0,
    decision_log_prefix_sha256="c" * 64,
    code_version=None,
    contract_version="0.2",
    silver_identity_version="1",
    python_version="3.12.14",
    sqlite_version="3.53.1",
)


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


class TestStoredPublication(GoldRepositoryContract):
    """The worked example, published to `gold.db` and opened again."""

    @pytest.fixture
    def repository(self, store: GoldStore) -> GoldRepository:
        store.publish(GoldResult(PUBLICATION, RECORDS), RECIPE, CONFIGURATION)
        return store.open(PUBLICATION.publication_id)
