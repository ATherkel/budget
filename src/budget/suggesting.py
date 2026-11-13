# Copyright 2026 Therkel
"""The `suggest-rules` application operation: the bank's own category labels.

It reads the persisted Silver result only: no Bronze store, no writer lock,
and never transaction text, only counts and sums of each bank label pair.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from budget.profiles import Profile
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


def bank_label_pairs(profile: Profile) -> tuple[BankLabelPair, ...]:
    """Return every labelled pair in Silver, by category then subcategory.

    A missing subcategory is a pair of its own, after the category's named ones.
    """
    with SilverStore(profile, read_only=True) as store:
        result = store.read()
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
    return tuple(pairs)
