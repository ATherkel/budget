# Copyright 2026 Therkel
"""`rules.toml`: the household's classification rules.

A rule is a pattern over one transaction's own facts: every `when` condition
must hold, and `then` assigns exactly one outcome (`classification.md`,
*Classification Rules*). File order never matters, so rules are keyed by ID.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Literal

from budget.inputs.document import ConfigurationError, file_problem, read_document
from budget.inputs.fields import FieldRule
from budget.profiles import (
    ACCOUNTS_FILE_NAME,
    RULES_FILE_NAME,
    TAXONOMY_FILE_NAME,
    Profile,
)


@dataclass(frozen=True)
class RuleConditions:
    """A rule's `when` table; an absent condition is `None` or empty.

    A description condition holds when the text matches any of its patterns.
    """

    account: str | None = None
    description_contains: tuple[str, ...] = ()
    description_starts_with: tuple[str, ...] = ()
    description_regex: tuple[str, ...] = ()
    amount_sign: Literal["negative", "positive"] | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    date_from: date | None = None
    date_to: date | None = None
    bank_category: str | None = None
    bank_subcategory: str | None = None


@dataclass(frozen=True)
class AssignCategory:
    """`then.category`: the type follows from its direction and the sign."""

    category_id: str


@dataclass(frozen=True)
class ClaimTransfer:
    """`then.transfer_claim = true`: a transfer only once it is paired."""


@dataclass(frozen=True)
class AssignAdjustment:
    """`then.adjustment`: an adjustment, with the reason lineage keeps."""

    reason: str


type RuleOutcome = AssignCategory | ClaimTransfer | AssignAdjustment


def _is_quoted_decimal(value: object) -> bool:
    """Accept a quoted, finite decimal such as `"-1000.00"`."""
    if not isinstance(value, str):
        return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


_AMOUNT = FieldRule(
    _is_quoted_decimal, "must be a quoted decimal, got a number", required=False
)
_AMOUNT_KEYS = ("amount_min", "amount_max")


@dataclass(frozen=True)
class Rule:
    """One `[[rule]]` block."""

    rule_id: str
    priority: int
    when: RuleConditions
    then: RuleOutcome


def _patterns(value: str | list[str] | None) -> tuple[str, ...]:
    """Read one pattern, or a list meaning any of them."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _amount(value: str | None) -> Decimal | None:
    """Read a quoted decimal amount."""
    return None if value is None else Decimal(value)


def _conditions(when: Mapping[str, Any]) -> RuleConditions:
    """Build a rule's conditions from its `when` table."""
    return RuleConditions(
        account=when.get("account"),
        description_contains=_patterns(when.get("description_contains")),
        description_starts_with=_patterns(when.get("description_starts_with")),
        description_regex=_patterns(when.get("description_regex")),
        amount_sign=when.get("amount_sign"),
        amount_min=_amount(when.get("amount_min")),
        amount_max=_amount(when.get("amount_max")),
        date_from=when.get("date_from"),
        date_to=when.get("date_to"),
        bank_category=when.get("bank_category"),
        bank_subcategory=when.get("bank_subcategory"),
    )


def _outcome(then: Mapping[str, Any]) -> RuleOutcome:
    """Build a rule's one outcome from its `then` table."""
    if "category" in then:
        return AssignCategory(then["category"])
    if "adjustment" in then:
        return AssignAdjustment(then["adjustment"])
    return ClaimTransfer()


def _rule(entry: Mapping[str, Any]) -> Rule:
    """Build one rule from its `[[rule]]` block."""
    return Rule(
        rule_id=entry["id"],
        priority=entry.get("priority", 0),
        when=_conditions(entry.get("when", {})),
        then=_outcome(entry["then"]),
    )


@dataclass(frozen=True)
class KnownIds:
    """The IDs other input files declare, which a rule may name."""

    accounts: Collection[str]
    categories: Collection[str]


def _reference_problems(entry: Mapping[str, Any], known: KnownIds) -> list[str]:
    """Name each account or category a rule refers to that no file declares."""
    references = (
        ("when", "account", known.accounts, ACCOUNTS_FILE_NAME),
        ("then", "category", known.categories, TAXONOMY_FILE_NAME),
    )
    problems = []
    for table, key, declared, file_name in references:
        value = entry.get(table, {}).get(key)
        if value is not None and value not in declared:
            problems.append(f'{table}.{key} "{value}" is not in {file_name}')
    return problems


def _rule_problems(entry: Mapping[str, Any], known: KnownIds) -> list[str]:
    """List one rule's problems, each naming the rule."""
    when = entry.get("when", {})
    problems = [
        f"when.{key} {_AMOUNT.rule}"
        for key in _AMOUNT_KEYS
        if key in when and not _AMOUNT.accepts(when[key])
    ]
    problems.extend(_reference_problems(entry, known))
    return [
        file_problem(RULES_FILE_NAME, f'rule "{entry["id"]}": {problem}')
        for problem in problems
    ]


def load_rules(profile: Profile, known: KnownIds) -> Mapping[str, Rule]:
    """Load the profile's `rules.toml`, keyed by rule ID.

    A rule may name only the accounts and categories `known` holds.
    """
    document = read_document(profile.input_file(RULES_FILE_NAME), RULES_FILE_NAME)
    entries = document.get("rule", [])
    problems = [
        problem for entry in entries for problem in _rule_problems(entry, known)
    ]
    if problems:
        raise ConfigurationError(tuple(problems))
    return MappingProxyType({rule.rule_id: rule for rule in map(_rule, entries)})
