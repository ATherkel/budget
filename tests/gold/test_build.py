# Copyright 2026 Therkel
"""`gold.build`: Gold records from Silver, the account registry and the taxonomy.

Nothing is classified yet, so every transaction is `unknown`. The expected
records are the worked example's (`gold-layer.md`), and the other cases are
synthetic. Records come in no fixed order, so they are compared as multisets.
"""

from collections import Counter

from tests.gold.worked_example import ACCOUNTS, CATEGORIES, PUBLICATION
from tests.gold.worked_silver import build_from


def test_the_registry_and_taxonomy_are_published_as_dimensions() -> None:
    result = build_from()

    assert result.publication() == PUBLICATION
    assert Counter(result.accounts()) == Counter(ACCOUNTS)
    assert Counter(result.categories()) == Counter(CATEGORIES)
