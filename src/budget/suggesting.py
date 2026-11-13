# Copyright 2026 Therkel
"""The `suggest-rules` application operation: the bank's own category labels.

It reads the persisted Silver result only: no Bronze store, no writer lock,
and never transaction text, only counts and sums of each bank label pair.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal

from budget.inputs.rule_checks import KnownIds
from budget.inputs.rules import Rule, RuleConditions, fold, load_rules
from budget.profiles import RULES_FILE_NAME, Profile
from budget.silver import SilverStore

type _Labels = tuple[str | None, str | None]


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
    counts: Counter[_Labels] = Counter()
    sums: defaultdict[_Labels, defaultdict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    for transaction in result.transactions:
        labels = (transaction.bank_category, transaction.bank_subcategory)
        counts[labels] += 1
        sums[labels][transaction.currency] += transaction.amount
    pairs = [
        BankLabelPair(
            category=category,
            subcategory=subcategory,
            transactions=n,
            sums=dict(sums[category, subcategory]),
            covered_by=_covering(label_rules, category, subcategory),
        )
        for (category, subcategory), n in counts.items()
        if category is not None
    ]
    pairs.sort(
        key=lambda pair: (
            pair.category,
            pair.subcategory is None,
            pair.subcategory or "",
        )
    )
    uncategorized = sum(n for (category, _), n in counts.items() if category is None)
    return BankLabels(pairs=tuple(pairs), uncategorized=uncategorized)


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
