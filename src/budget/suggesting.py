# Copyright 2026 Therkel
"""The `suggest-rules` application operation: the bank's own category labels.

It reads the persisted Silver result only: no Bronze store, no writer lock,
and never transaction text, only counts of each bank label pair.
"""

from collections import Counter
from dataclasses import dataclass

from budget.profiles import Profile
from budget.silver import SilverStore


@dataclass(frozen=True)
class BankLabelPair:
    """One (bank_category, bank_subcategory) pair and its transactions."""

    category: str
    subcategory: str | None
    transactions: int


def bank_label_pairs(profile: Profile) -> tuple[BankLabelPair, ...]:
    """Return every labelled pair in Silver, by category then subcategory.

    A missing subcategory is a pair of its own, after the category's named ones.
    """
    with SilverStore(profile, read_only=True) as store:
        result = store.read()
    counts = Counter(
        (transaction.bank_category, transaction.bank_subcategory)
        for transaction in result.transactions
    )
    pairs = [
        BankLabelPair(category=category, subcategory=subcategory, transactions=n)
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
