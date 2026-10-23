# Copyright 2026 Therkel
"""The recipe and configuration a test publishes the worked example under."""

from budget.gold.recipe import Recipe, RecipeImportRun
from budget.inputs import ConfigurationSnapshot
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
