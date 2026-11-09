# Copyright 2026 Therkel
"""Publishing the synthetic worked example to a Gold store, for any test.

`RECIPE` names the worked example's inputs and `CONFIGURATION`, whose
fingerprint it records; neither is any real household's.
"""

from dataclasses import replace

from budget.gold import GoldPublication, GoldResult
from budget.gold.recipe import Recipe, RecipeImportRun
from budget.gold.store import GoldStore
from budget.inputs import ConfigurationSnapshot
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
    late_booking_days=7,
    python_version="3.12.14",
    sqlite_version="3.53.1",
)


def publication(publication_id: int) -> GoldPublication:
    """The worked example's publication metadata, under another id."""
    return replace(PUBLICATION, publication_id=publication_id)


def publish(store: GoldStore, publication_id: int) -> GoldPublication:
    """Publish the worked example as `publication_id`, and return its metadata."""
    published = publication(publication_id)
    store.publish(GoldResult(published, RECORDS), RECIPE, CONFIGURATION)
    return published
