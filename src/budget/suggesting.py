# Copyright 2026 Therkel
"""The `suggest-rules` application operation: the bank's own category labels.

It reads the persisted Silver result only: no Bronze store, no writer lock.
It never returns transaction text, only counts and sums of each bank label pair.
"""

import json
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Final

from budget.inputs.rule_checks import KnownIds
from budget.inputs.rules import Rule, RuleConditions, fold, load_rules
from budget.profiles import RULES_FILE_NAME, Profile
from budget.silver import SilverStore

type _Labels = tuple[str, str | None]


@dataclass(frozen=True)
class BankLabelPair:
    """One (bank_category, bank_subcategory) pair and its transactions."""

    category: str
    subcategory: str | None
    transactions: int
    # The signed sum of the pair's amounts in each currency, never added
    # across currencies.
    sums: Mapping[str, Decimal]
    # The rules that test nothing but the bank's labels and match this pair.
    covered_by: tuple[str, ...]
    # The pair's other spellings, which differ from it only in case, most-used
    # first. The pair itself carries the most-used one.
    other_spellings: tuple[tuple[str, str | None], ...] = ()


class SilverNotBuiltForSuggestionsError(RuntimeError):
    """Silver was never built, so it holds no bank labels to summarize."""

    def __init__(self) -> None:
        """Say which command builds Silver first."""
        super().__init__(
            "Silver has not been built, so there are no bank labels to "
            "summarize; run `budget rebuild --from silver` first"
        )


@dataclass(frozen=True)
class BankLabels:
    """Every bank label pair in Silver, and the transactions with no category."""

    pairs: tuple[BankLabelPair, ...]
    uncategorized: int


def bank_labels(profile: Profile) -> BankLabels:
    """Return every labelled pair in Silver, by category then subcategory.

    A missing subcategory is a pair of its own, after the category's named ones.
    A transaction with no bank category is in no pair, only in the count.
    """
    with SilverStore(profile, read_only=True) as store:
        if not store.is_built():
            raise SilverNotBuiltForSuggestionsError
        result = store.read()
    label_rules = _label_rules(profile)
    spellings: defaultdict[_Labels, Counter[_Labels]] = defaultdict(Counter)
    sums: defaultdict[_Labels, defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    uncategorized = 0
    for transaction in result.transactions:
        if transaction.bank_category is None:
            uncategorized += 1
            continue
        labels = (transaction.bank_category, transaction.bank_subcategory)
        folded = _folded(labels)
        spellings[folded][labels] += 1
        sums[folded][transaction.currency] += transaction.amount
    pairs = [
        _pair(spelled, sums[folded], label_rules)
        for folded, spelled in sorted(
            spellings.items(),
            key=lambda item: (item[0][0], item[0][1] is None, item[0][1] or ""),
        )
    ]
    return BankLabels(pairs=tuple(pairs), uncategorized=uncategorized)


TAXONOMY_DRAFT_NAME: Final = "taxonomy-draft.toml"
RULES_DRAFT_NAME: Final = "rules-draft.toml"
_DANISH_LETTERS: Final = (("æ", "ae"), ("ø", "oe"), ("å", "aa"))
# The transaction types that carry no category; `taxonomy.toml` refuses a
# category with one of these IDs, so no draft ID takes one.
_UNCATEGORISED_TYPES: Final = frozenset({"transfer", "adjustment", "unknown"})


def write_drafts(labels: BankLabels, out: Path) -> None:
    """Write a draft taxonomy and draft rules for every pair into `out`.

    One group per bank category and one category and rule per pair. The
    household edits both before copying them into its inputs.
    """
    taxonomy = ["format = 1", ""]
    rules = ["format = 1", ""]
    groups: dict[str, str] = {}
    taken_categories: set[str] = set()
    for pair in labels.pairs:
        if pair.category not in groups:
            groups[pair.category] = _unique(_slug(pair.category), set(groups.values()))
            taxonomy += [
                f"[group.{groups[pair.category]}]",
                f"name = {_toml_string(pair.category)}",
                f'direction = "{_direction(labels, pair.category)}"',
                "",
            ]
        category_id = _unique(
            f"{groups[pair.category]}-{_slug(pair.subcategory or 'other')}",
            taken_categories,
        )
        taken_categories.add(category_id)
        taxonomy += [
            _size_comment(pair),
            f"[category.{category_id}]",
            f"name = {_toml_string(pair.subcategory or pair.category)}",
            f"group = {_toml_string(groups[pair.category])}",
            "",
        ]
        rules += [
            "[[rule]]",
            f"id = {_toml_string('r-bank-' + category_id)}",
            "priority = -10" if pair.subcategory else "priority = -20",
            f"when.bank_category = {_toml_string(pair.category)}",
        ]
        if pair.subcategory is not None:
            rules.append(f"when.bank_subcategory = {_toml_string(pair.subcategory)}")
        rules += [f"then.category = {_toml_string(category_id)}", ""]
    out.mkdir(parents=True, exist_ok=True)
    (out / TAXONOMY_DRAFT_NAME).write_text(
        "\n".join(taxonomy), encoding="utf-8", newline="\n"
    )
    (out / RULES_DRAFT_NAME).write_text(
        "\n".join(rules), encoding="utf-8", newline="\n"
    )


def _direction(labels: BankLabels, category: str) -> str:
    """Guess a group's direction: income only if each currency's sum is positive.

    Currencies are never added together, so a group with a negative sum in
    any currency, or a zero one, is an expense.
    """
    sums: defaultdict[str, Decimal] = defaultdict(Decimal)
    for pair in labels.pairs:
        if pair.category == category:
            for currency, total in pair.sums.items():
                sums[currency] += total
    return "income" if all(total > 0 for total in sums.values()) else "expense"


def _size_comment(pair: BankLabelPair) -> str:
    """Say how many transactions a pair holds and their sum in each currency."""
    noun = "transaction" if pair.transactions == 1 else "transactions"
    sums = ", ".join(
        f"{total} {currency}" for currency, total in sorted(pair.sums.items())
    )
    return f"# {pair.transactions} {noun}, {sums}"


def _slug(text: str) -> str:
    """Make a durable ASCII ID from a label: lower case, words joined by `-`.

    æ, ø and å spell out as Danish does; other letters lose their accents.
    """
    text = text.lower()
    for letter, spelled in _DANISH_LETTERS:
        text = text.replace(letter, spelled)
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    words = "".join(ch if ch.isalnum() else " " for ch in ascii_text).split()
    return "-".join(words) or "x"


def _unique(wanted: str, taken: set[str]) -> str:
    """Return `wanted`, suffixed `-2`, `-3`… past any taken or reserved ID."""
    candidate, n = wanted, 2
    while candidate in taken or candidate in _UNCATEGORISED_TYPES:
        candidate, n = f"{wanted}-{n}", n + 1
    return candidate


def _toml_string(text: str) -> str:
    """`text` as a TOML basic string; a JSON string is one."""
    return json.dumps(text, ensure_ascii=False)


def _folded(labels: _Labels) -> _Labels:
    """Fold both labels, as Gold matches a label: without its case."""
    category, subcategory = labels
    return fold(category), None if subcategory is None else fold(subcategory)


def _pair(
    spelled: Counter[_Labels],
    sums: Mapping[str, Decimal],
    label_rules: tuple[Rule, ...],
) -> BankLabelPair:
    """Build one pair from its spellings; the most-used, then the first, leads."""
    ordered = sorted(
        spelled, key=lambda labels: (-spelled[labels], labels[0], labels[1] or "")
    )
    category, subcategory = ordered[0]
    return BankLabelPair(
        category=category,
        subcategory=subcategory,
        transactions=spelled.total(),
        sums=dict(sums),
        covered_by=_covering(label_rules, category, subcategory),
        other_spellings=tuple(ordered[1:]),
    )


def _label_rules(profile: Profile) -> tuple[Rule, ...]:
    """Return the rules in `rules.toml` that test nothing but the bank's labels.

    A missing `rules.toml` holds no rules; an invalid one is refused. It is
    judged on its own, so another input file's state never matters here.
    """
    if not profile.input_file(RULES_FILE_NAME).exists():
        return ()
    rules = load_rules(profile, KnownIds(accounts=None, categories=None))
    return tuple(
        rule
        for rule in rules.values()
        if rule.when.bank_category is not None
        and replace(rule.when, bank_category=None, bank_subcategory=None)
        == RuleConditions()
    )


def _covering(
    rules: tuple[Rule, ...], category: str, subcategory: str | None
) -> tuple[str, ...]:
    """Return the IDs of the rules that match the pair, as Gold matches a label."""
    return tuple(
        sorted(
            rule.rule_id
            for rule in rules
            if rule.when.folded_bank_category == fold(category)
            and (
                rule.when.bank_subcategory is None
                or (
                    subcategory is not None
                    and rule.when.folded_bank_subcategory == fold(subcategory)
                )
            )
        )
    )
