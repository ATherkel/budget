# Copyright 2026 Therkel
"""The configuration snapshot a recipe fingerprints (`publications.md`).

`load_configuration` reads the account registry, the taxonomy and the rules,
checks each against the others, and lists every problem in all three before
stopping.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from budget.inputs.accounts import Account, load_accounts
from budget.inputs.rules import Rule, load_rules
from budget.inputs.taxonomy import Taxonomy, load_taxonomy
from budget.profiles import Profile


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """The parsed configuration a Gold build classifies with."""

    accounts: Mapping[str, Account]
    taxonomy: Taxonomy
    rules: Mapping[str, Rule]


def load_configuration(profile: Profile) -> ConfigurationSnapshot:
    """Load and cross-check the profile's accounts, taxonomy and rules."""
    return ConfigurationSnapshot(
        accounts=load_accounts(profile),
        taxonomy=load_taxonomy(profile),
        rules=load_rules(profile),
    )
