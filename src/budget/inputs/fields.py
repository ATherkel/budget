# Copyright 2026 Therkel
"""What the keys of one input table must hold, and how a problem says so.

A table's rules are data: a mapping from each key it may carry to a
`FieldRule`. `key_problems` judges a table against them, so every input file
reports an unknown, invalid or missing key in the same words.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import TypeGuard

# A durable ID: lowercase ASCII words joined by single hyphens.
_DURABLE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class FieldRule:
    """What one key must hold, and how a problem says so."""

    accepts: Callable[[object], bool]
    rule: str
    required: bool = True


def is_durable_id(value: str) -> bool:
    """Accept lowercase words joined by single hyphens, such as `joint-current`."""
    return _DURABLE_ID.fullmatch(value) is not None


def is_text(value: object) -> TypeGuard[str]:
    """Accept a non-empty TOML string."""
    return isinstance(value, str) and value != ""


def is_date(value: object) -> bool:
    """Accept a TOML local date; a date-time is a different value."""
    return isinstance(value, date) and not isinstance(value, datetime)


def one_of(*choices: str) -> FieldRule:
    """Accept exactly one of the given strings."""
    return FieldRule(
        accepts=lambda value: value in choices,
        rule=f"must be one of {', '.join(choices)}",
    )


TEXT = FieldRule(is_text, "must be a non-empty string")


def key_problems(
    table: Mapping[str, object], fields: Mapping[str, FieldRule], prefix: str = ""
) -> list[str]:
    """List a table's unknown and invalid keys in file order, then missing ones.

    `prefix` names a nested table's keys the way the file spells them, such as
    `when.` for `when.account`.
    """
    problems = []
    for key, value in table.items():
        field_rule = fields.get(key)
        if field_rule is None:
            problems.append(f'unknown key "{prefix}{key}"')
        elif not field_rule.accepts(value):
            problems.append(f"{prefix}{key} {field_rule.rule}")
    problems.extend(
        f"{prefix}{key} is missing"
        for key, field_rule in fields.items()
        if field_rule.required and key not in table
    )
    return problems
