# Copyright 2026 Therkel
"""The `suggest-rules` application operation: the bank's own category labels.

It reads the persisted Silver result only: no Bronze store, no writer lock.
It never returns transaction text, only counts and sums of each bank label pair.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal

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
