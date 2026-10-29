# Copyright 2026 Therkel
"""What a `rules.toml` block must hold, and the problems that name each rule.

Every key of a `[[rule]]` block, its `when` conditions and its `then` outcome
is judged by field rules. A rule may name only an account or category another
input file declares (`operations.md`, *Household Inputs*).
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from budget.inputs.document import file_problem
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
from budget.profiles import ACCOUNTS_FILE_NAME, RULES_FILE_NAME, TAXONOMY_FILE_NAME


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


def _is_reason(value: object) -> bool:
    """Accept a reason lineage can keep: text that is not only blanks."""
    return isinstance(value, str) and value.strip() != ""


# Every outcome a rule's `then` table may hold; it holds exactly one.
_THEN_FIELDS: Mapping[str, FieldRule] = MappingProxyType(
    {
        "category": optional(TEXT),
        "transfer_claim": FieldRule(
            lambda value: value is True, "must be true", required=False
        ),
        "adjustment": FieldRule(_is_reason, "must give a reason", required=False),
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
class KnownIds:
    """The IDs other input files declare, which a rule may name.

    `None` stands for a file that was itself refused: it declares nothing a
    rule can be checked against, so no reference into it is judged.
    """

    accounts: Collection[str] | None
    categories: Collection[str] | None


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
        if declared is not None and is_text(value) and value not in declared:
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


def rules_problems(entries: list[object], known: KnownIds) -> list[str]:
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
