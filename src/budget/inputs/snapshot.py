# Copyright 2026 Therkel
"""The configuration snapshot a recipe fingerprints (`publications.md`).

`load_configuration` reads the account registry, the taxonomy and the rules,
checks each against the others, and lists every problem in all three before
stopping.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from budget.inputs.accounts import Account, load_accounts
from budget.inputs.document import ConfigurationError
from budget.inputs.rules import KnownIds, Rule, load_rules
from budget.inputs.taxonomy import Taxonomy, load_taxonomy
from budget.profiles import Profile


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """The parsed configuration a Gold build classifies with."""

    accounts: Mapping[str, Account]
    taxonomy: Taxonomy
    rules: Mapping[str, Rule]


def _attempt[T](load: Callable[[], T], problems: list[str]) -> T | None:
    """Load one file, or keep its problems and give nothing."""
    try:
        return load()
    except ConfigurationError as error:
        problems.extend(error.problems)
        return None


def load_configuration(profile: Profile) -> ConfigurationSnapshot:
    """Load and cross-check the profile's accounts, taxonomy and rules.

    Every file is judged even when an earlier one is refused, so one error
    lists every problem. A refused file declares nothing a rule can be checked
    against, so no reference into it is judged.
    """
    problems: list[str] = []
    accounts = _attempt(lambda: load_accounts(profile), problems)
    taxonomy = _attempt(lambda: load_taxonomy(profile), problems)
    known = KnownIds(
        accounts=None if accounts is None else accounts.keys(),
        categories=None if taxonomy is None else taxonomy.categories.keys(),
    )
    rules = _attempt(lambda: load_rules(profile, known), problems)
    if accounts is None or taxonomy is None or rules is None:
        raise ConfigurationError(tuple(problems))
    return ConfigurationSnapshot(accounts=accounts, taxonomy=taxonomy, rules=rules)
