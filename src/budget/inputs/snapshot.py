# Copyright 2026 Therkel
"""The configuration snapshot a recipe fingerprints (`publications.md`).

`load_configuration` reads the account registry, the taxonomy and the rules,
checks each against the others, and lists every problem in all three before
stopping.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal

from budget.inputs.accounts import Account, load_accounts
from budget.inputs.document import ConfigurationError
from budget.inputs.rules import (
    AssignAdjustment,
    AssignCategory,
    ClaimTransfer,
    KnownIds,
    Rule,
    RuleOutcome,
    load_rules,
)
from budget.inputs.taxonomy import Taxonomy, load_taxonomy
from budget.profiles import Profile


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """The parsed configuration a Gold build classifies with."""

    accounts: Mapping[str, Account]
    taxonomy: Taxonomy
    rules: Mapping[str, Rule]

    @property
    def fingerprint(self) -> str:
        """The SHA-256 of the snapshot's canonical content, in hexadecimal.

        The content is what the files mean, not how they are written: keys and
        entries in any order, any TOML spelling, and an amount's trailing zeros
        all give the same fingerprint.
        """
        canonical = json.dumps(
            _canonical(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=_json_value,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_amount(amount: Decimal) -> str:
    """Write an amount exactly, without trailing zeros or a negative zero.

    Formatting a `Decimal` without a precision is exact, so no amount is
    rounded to the decimal context's 28 digits: -1000.00 and -1000 are one
    amount, and every two different amounts stay two.
    """
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _json_value(value: object) -> str:
    """Write a value JSON has no type for: a decimal amount or a date."""
    if isinstance(value, Decimal):
        return _canonical_amount(value)
    if isinstance(value, date):
        return value.isoformat()
    message = f"no canonical form for {type(value).__name__}"
    raise TypeError(message)


def _canonical_outcome(outcome: RuleOutcome) -> dict[str, object]:
    """Spell an outcome as `rules.toml` does."""
    match outcome:
        case AssignCategory(category_id=category_id):
            return {"category": category_id}
        case ClaimTransfer():
            return {"transfer_claim": True}
        case AssignAdjustment(reason=reason):
            return {"adjustment": reason}


def _canonical_rule(rule: Rule) -> dict[str, object]:
    """Spell a rule; a condition's patterns are any of them, so their order is not."""
    when = {
        key: sorted(set(value)) if isinstance(value, tuple) else value
        for key, value in asdict(rule.when).items()
    }
    return {
        "priority": rule.priority,
        "when": when,
        "then": _canonical_outcome(rule.then),
    }


def _canonical(snapshot: ConfigurationSnapshot) -> dict[str, object]:
    """Spell the snapshot's meaning as plain values; JSON sorts every key."""
    return {
        "accounts": {
            account_id: asdict(account)
            for account_id, account in snapshot.accounts.items()
        },
        "groups": {
            group_id: asdict(group)
            for group_id, group in snapshot.taxonomy.groups.items()
        },
        "categories": {
            category_id: asdict(category)
            for category_id, category in snapshot.taxonomy.categories.items()
        },
        "rules": {
            rule_id: _canonical_rule(rule) for rule_id, rule in snapshot.rules.items()
        },
    }


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
