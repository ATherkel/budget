# Copyright 2026 Therkel
"""The configuration snapshot a recipe fingerprints (`publications.md`).

`load_configuration` reads the account registry, the taxonomy and the rules,
checks each against the others, and lists every problem in all three before
stopping.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    RuleConditions,
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


def _set(table: Mapping[str, object]) -> dict[str, object]:
    """Keep only the keys a file set, so a new optional key changes nothing."""
    return {key: value for key, value in table.items() if value not in (None, [])}


def _any_of(patterns: tuple[str, ...]) -> list[str]:
    """Spell patterns a condition holds when any matches: their order is not."""
    return sorted(set(patterns))


def _canonical_when(when: RuleConditions) -> dict[str, object]:
    """Spell a rule's conditions as `rules.toml` does."""
    return _set(
        {
            "account": when.account,
            "description_contains": _any_of(when.description_contains),
            "description_starts_with": _any_of(when.description_starts_with),
            "description_regex": _any_of(when.description_regex),
            "amount_sign": when.amount_sign,
            "amount_min": when.amount_min,
            "amount_max": when.amount_max,
            "date_from": when.date_from,
            "date_to": when.date_to,
            "bank_category": when.bank_category,
            "bank_subcategory": when.bank_subcategory,
        }
    )


def _canonical_rule(rule: Rule) -> dict[str, object]:
    """Spell a rule as `rules.toml` does, its ID being its key."""
    return {
        "priority": rule.priority,
        "when": _canonical_when(rule.when),
        "then": _canonical_outcome(rule.then),
    }


def _canonical_account(account: Account) -> dict[str, object]:
    """Spell an account as `accounts.toml` does, its ID being its key."""
    return _set(
        {
            "display_name": account.display_name,
            "account_type": account.account_type,
            "ownership_scope": account.ownership_scope,
            "currency": account.currency,
            "source_format": account.source_format,
            "bank_account_number": account.bank_account_number,
            "closed_on": account.closed_on,
        }
    )


def _canonical(snapshot: ConfigurationSnapshot) -> dict[str, object]:
    """Spell the snapshot as its files do; JSON sorts every key.

    Each value is written out key by key, never from the Python field names,
    so renaming a field leaves every fingerprint as it was.
    """
    taxonomy = snapshot.taxonomy
    return {
        "accounts": {
            account_id: _canonical_account(account)
            for account_id, account in snapshot.accounts.items()
        },
        "groups": {
            group_id: {"name": group.name, "direction": group.direction}
            for group_id, group in taxonomy.groups.items()
        },
        "categories": {
            category_id: {"name": category.name, "group": category.group_id}
            for category_id, category in taxonomy.categories.items()
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
