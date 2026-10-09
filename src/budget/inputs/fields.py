# Copyright 2026 Therkel
"""What the keys of one input table must hold, and how a problem says so.

A table's rules are data: a mapping from each key it may carry to a
`FieldRule`. `key_problems` judges a table against them, so every input file
reports an unknown, invalid or missing key in the same words.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TypeGuard

# A durable ID: lowercase ASCII words joined by single hyphens.
_DURABLE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class FieldRule:
    """What one key must hold, and how a problem says so.

    `explain`, when set, words the problem from the refused value itself.
    """

    accepts: Callable[[object], bool]
    rule: str
    required: bool = True
    explain: Callable[[object], str] | None = None

    def refusal(self, value: object) -> str:
        """Say what a refused value breaks."""
        return self.rule if self.explain is None else self.explain(value)


def optional(field_rule: FieldRule) -> FieldRule:
    """Relax a rule for a key a table may leave out."""
    return replace(field_rule, required=False)


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


def is_quoted_decimal(value: object) -> bool:
    """Accept a quoted, finite decimal such as `"-1000.00"`."""
    if not isinstance(value, str):
        return False
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def _amount_refusal(value: object) -> str:
    """Say why an amount is refused; a TOML number is never one.

    TOML reads an unquoted `1000.00` as a binary floating-point number, which
    money never accepts (`operations.md`, *Household Inputs*).
    """
    if isinstance(value, int | float) and not isinstance(value, bool):
        return "must be a quoted decimal, got a number"
    return 'must be a quoted decimal such as "-1000.00"'


TEXT = FieldRule(is_text, "must be a non-empty string")
DATE = FieldRule(is_date, "must be a date such as 2026-01-31")
AMOUNT = FieldRule(
    is_quoted_decimal, "must be a quoted decimal", explain=_amount_refusal
)


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
            problems.append(f"{prefix}{key} {field_rule.refusal(value)}")
    problems.extend(
        f"{prefix}{key} is missing"
        for key, field_rule in fields.items()
        if field_rule.required and key not in table
    )
    return problems
