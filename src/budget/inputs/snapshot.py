# Copyright 2026 Therkel
"""The configuration snapshot a recipe fingerprints (`publications.md`).

`load_configuration` reads the account registry, the taxonomy and the rules,
checks each against the others, and lists every problem in all three before
stopping.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from budget.inputs.accounts import Account
from budget.inputs.rules import Rule
from budget.inputs.taxonomy import Taxonomy
from budget.profiles import Profile


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """The parsed configuration a Gold build classifies with."""

    accounts: Mapping[str, Account]
    taxonomy: Taxonomy
    rules: Mapping[str, Rule]


def load_configuration(profile: Profile) -> ConfigurationSnapshot:
    """Load and cross-check the profile's accounts, taxonomy and rules."""
    raise NotImplementedError(profile)
