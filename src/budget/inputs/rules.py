# Copyright 2026 Therkel
"""`rules.toml`: the household's classification rules.

A rule is a pattern over one transaction's own facts: every `when` condition
must hold, and `then` assigns exactly one outcome (`classification.md`,
*Classification Rules*). File order never matters, so rules are keyed by ID.
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Literal

from budget.inputs.document import (
    ConfigurationError,
    file_problem,
    read_document,
    unknown_top_level_keys,
)
from budget.inputs.fields import (
    AMOUNT,
    DATE,
    TEXT,
    FieldRule,
    is_durable_id,
    is_text,
    key_problems,
    one_of,
    optional,
)
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


def _pattern_list(value: object) -> list[object] | None:
    """Read one pattern or a list of them as a list; `None` for anything else."""
    if isinstance(value, str):
        return [value]
    return list[object](value) if isinstance(value, list) else None


def _is_patterns(value: object) -> bool:
    """Accept a non-empty string, or a non-empty list of them."""
    patterns = _pattern_list(value)
    return bool(patterns) and all(map(is_text, patterns or ()))


def _compiles(pattern: object) -> bool:
    """Accept a regular expression as a rule applies it: case-insensitively."""
    try:
        re.compile(str(pattern), re.IGNORECASE)
    except re.error:
        return False
    return True


def _is_regexes(value: object) -> bool:
    """Accept patterns that are each a valid regular expression."""
    return _is_patterns(value) and all(map(_compiles, _pattern_list(value) or ()))


_PATTERNS = FieldRule(
    _is_patterns, "must be a non-empty string or a list of them", required=False
)

# Every condition a rule's `when` table may hold; each is optional.
_WHEN_FIELDS: Mapping[str, FieldRule] = MappingProxyType(
    {
        "account": optional(TEXT),
        "description_contains": _PATTERNS,
        "description_starts_with": _PATTERNS,
        "description_regex": FieldRule(
            _is_regexes, "must hold valid regular expressions", required=False
        ),
        "amount_sign": optional(one_of("negative", "positive")),
        "amount_min": optional(AMOUNT),
        "amount_max": optional(AMOUNT),
        "date_from": optional(DATE),
        "date_to": optional(DATE),
        "bank_category": optional(TEXT),
        "bank_subcategory": optional(TEXT),
    }
)

# Every outcome a rule's `then` table may hold; it holds exactly one.
_THEN_FIELDS: Mapping[str, FieldRule] = MappingProxyType(
    {
        "category": optional(TEXT),
        "transfer_claim": FieldRule(
            lambda value: value is True, "must be true", required=False
        ),
        "adjustment": optional(TEXT),
    }
)
_ONE_OUTCOME = f"then must hold exactly one of {', '.join(_THEN_FIELDS)}"


def _is_integer(value: object) -> bool:
    """Accept a TOML integer; `bool` is a subclass of `int` in Python, and is not."""
    return type(value) is int


# A key whose value is judged apart, by `_when_problems` or `_then_problems`.
_JUDGED_APART = FieldRule(lambda _: True, "", required=False)

# Every key a `[[rule]]` block may carry.
_RULE_FIELDS: Mapping[str, FieldRule] = MappingProxyType(
    {
        "id": TEXT,
        "priority": FieldRule(_is_integer, "must be an integer", required=False),
        "when": _JUDGED_APART,
        "then": _JUDGED_APART,
    }
)


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
        values = entry.get(table)
        # A value of the wrong type has its own problem, and names nothing.
        value = values.get(key) if isinstance(values, dict) else None
        if is_text(value) and value not in declared:
            problems.append(f'{table}.{key} "{value}" is not in {file_name}')
    return problems


def _when_problems(entry: Mapping[str, Any]) -> list[str]:
    """List the problems in a rule's conditions."""
    when = entry.get("when", {})
    if not isinstance(when, dict):
        return ["when must be a table of conditions"]
    return key_problems(when, _WHEN_FIELDS, prefix="when.")


def _then_problems(entry: Mapping[str, Any]) -> list[str]:
    """List the problems in a rule's outcome."""
    then = entry.get("then", {})
    if not isinstance(then, dict):
        return [_ONE_OUTCOME]
    problems = key_problems(then, _THEN_FIELDS, prefix="then.")
    if sum(key in then for key in _THEN_FIELDS) != 1:
        problems.append(_ONE_OUTCOME)
    return problems


def _id_problems(rule_id: object, earlier: Collection[str]) -> list[str]:
    """Name an ID of the wrong shape, or one an earlier rule already uses.

    An ID that is not a string at all is a key problem of its own.
    """
    if not is_text(rule_id):
        return []
    if not is_durable_id(rule_id):
        return ["the ID must be lowercase words joined by hyphens, such as r-netto"]
    if rule_id in earlier:
        return ["the ID is already used by an earlier rule"]
    return []


def _rule_problems(
    entry: object, known: KnownIds, earlier: Collection[str]
) -> list[str]:
    """List one rule's problems: its ID, its keys, then its tables."""
    if not isinstance(entry, dict):
        return ["must be a table of keys"]
    problems = _id_problems(entry.get("id"), earlier)
    problems.extend(key_problems(entry, _RULE_FIELDS))
    problems.extend(_when_problems(entry))
    problems.extend(_then_problems(entry))
    problems.extend(_reference_problems(entry, known))
    return problems


def _rule_id(entry: object) -> str | None:
    """Return the rule's ID, if it has a usable one."""
    rule_id = entry.get("id") if isinstance(entry, dict) else None
    return rule_id if is_text(rule_id) else None


def _rules_problems(entries: list[object], known: KnownIds) -> list[str]:
    """List every rule's problems in file order, each naming its rule.

    A rule without a usable ID is named by its position, counting from 1.
    """
    problems = []
    earlier: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        rule_id = _rule_id(entry)
        label = f"rule {position}" if rule_id is None else f'rule "{rule_id}"'
        problems.extend(
            file_problem(RULES_FILE_NAME, f"{label}: {problem}")
            for problem in _rule_problems(entry, known, earlier)
        )
        if rule_id is not None:
            earlier.add(rule_id)
    return problems


def load_rules(profile: Profile, known: KnownIds) -> Mapping[str, Rule]:
    """Load the profile's `rules.toml`, keyed by rule ID.

    A rule may name only the accounts and categories `known` holds.
    """
    document = read_document(profile.input_file(RULES_FILE_NAME), RULES_FILE_NAME)
    problems = unknown_top_level_keys(document, RULES_FILE_NAME, ("rule",))
    entries = document.get("rule", [])
    if not isinstance(entries, list):
        problems.append(
            file_problem(RULES_FILE_NAME, "rule must hold one [[rule]] block per rule")
        )
        entries = []
    problems.extend(_rules_problems(entries, known))
    if problems:
        raise ConfigurationError(tuple(problems))
    return MappingProxyType({rule.rule_id: rule for rule in map(_rule, entries)})
