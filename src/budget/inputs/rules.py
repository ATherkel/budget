# Copyright 2026 Therkel
"""`rules.toml`: the household's classification rules.

A rule is a pattern over one transaction's own facts: every `when` condition
must hold, and `then` assigns exactly one outcome (`classification.md`,
*Classification Rules*). File order never matters, so rules are keyed by ID.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


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


@dataclass(frozen=True)
class Rule:
    """One `[[rule]]` block."""

    rule_id: str
    priority: int
    when: RuleConditions
    then: RuleOutcome
