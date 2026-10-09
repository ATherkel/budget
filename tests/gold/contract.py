# Copyright 2026 Therkel
"""Contract tests every `GoldRepository` implementation passes unchanged.

An implementation's test module subclasses `GoldRepositoryContract` and
provides a `repository` fixture holding the worked example
(`tests/gold/worked_example.py`). The contract fixes no order for returned
records, so the tests compare them as multisets.
"""

from collections import Counter
from datetime import date

from budget.gold import GoldRepository
from tests.gold.worked_example import example_transactions


class GoldRepositoryContract:
    """`gold-contract.md`, *Consumer Interface*, over the worked example."""

    def test_transactions_are_those_dated_within_an_inclusive_range(
        self, repository: GoldRepository
    ) -> None:
        found = repository.transactions(
            start_date=date(2026, 1, 20), end_date=date(2026, 2, 2)
        )

        assert Counter(found) == Counter(
            example_transactions(
                "current-02", "savings-01", "current-03", "current-04", "current-05"
            )
        )
