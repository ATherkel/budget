# Copyright 2026 Therkel
"""`rules.toml`: the household's classification rules.

A rule is a pattern over one transaction's own facts: every `when` condition
must hold, and `then` assigns exactly one outcome (`classification.md`,
*Classification Rules*). File order never matters, so rules are keyed by ID.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
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
from budget.inputs.rule_checks import KnownIds, rules_problems
from budget.profiles import RULES_FILE_NAME, Profile


def fold(text: str) -> str:
    """Fold text as a literal pattern matches it: without its case.

    The one fold both sides of a match use, so a pattern and a description can
    never be folded two different ways; `casefold`, unlike `lower`, also
    makes "ß" and "SS" one text.
    """
    return text.casefold()


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

    @property
    def folded_contains(self) -> tuple[str, ...]:
        """The `description_contains` patterns, folded."""
        return tuple(map(fold, self.description_contains))

    @property
    def folded_starts_with(self) -> tuple[str, ...]:
        """The `description_starts_with` patterns, folded."""
        return tuple(map(fold, self.description_starts_with))

    @property
    def folded_bank_category(self) -> str | None:
        """The `bank_category` label, folded, or `None` when it is unset."""
        return None if self.bank_category is None else fold(self.bank_category)

    @property
    def folded_bank_subcategory(self) -> str | None:
        """The `bank_subcategory` label, folded, or `None` when it is unset."""
        return None if self.bank_subcategory is None else fold(self.bank_subcategory)

    @property
    def sets_a_condition(self) -> bool:
        """Say whether the rule sets any condition at all.

        It reads every field, so a condition added later cannot be left out.
        """
        return any(getattr(self, f.name) not in (None, ()) for f in fields(self))

    def matches_description(self, description: str) -> bool:
        """Say whether the description meets every text condition the rule sets.

        A condition the rule leaves empty holds, so a rule that sets none
        holds for every description. For the literal patterns the description is
        folded as they are, so the match is the one the configuration
        fingerprint assumes (`classification.md`); a regex is searched as
        written, ignoring case, since folding it could change its meaning.
        """
        text = fold(description)

        contains = not self.folded_contains or any(
            pattern in text for pattern in self.folded_contains
        )
        starts_with = not self.folded_starts_with or any(
            text.startswith(pattern) for pattern in self.folded_starts_with
        )
        regex = not self.description_regex or any(
            re.search(pattern, description, re.IGNORECASE)
            for pattern in self.description_regex
        )
        return contains and starts_with and regex


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
    problems.extend(rules_problems(entries, known))
    if problems:
        raise ConfigurationError(tuple(problems))
    return MappingProxyType({rule.rule_id: rule for rule in map(_rule, entries)})
