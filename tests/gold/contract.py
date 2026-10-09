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
from tests.gold.worked_example import (
    SAVINGS,
    example_allocations,
    example_transactions,
)


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

    def test_transactions_are_only_those_of_the_named_accounts(
        self, repository: GoldRepository
    ) -> None:
        found = repository.transactions(
            start_date=date(2026, 1, 20),
            end_date=date(2026, 2, 2),
            account_ids=[SAVINGS],
        )

        assert Counter(found) == Counter(example_transactions("savings-01"))

    def test_category_allocations_are_filtered_like_transactions(
        self, repository: GoldRepository
    ) -> None:
        february = repository.category_allocations(
            start_date=date(2026, 2, 2), end_date=date(2026, 2, 25)
        )
        savings = repository.category_allocations(
            start_date=date(2026, 1, 20),
            end_date=date(2026, 4, 30),
            account_ids=[SAVINGS],
        )

        # gold-layer.md writes February's allocations out in full.
        assert Counter(february) == Counter(
            example_allocations(
                "current-04/rent",
                "current-05/groceries",
                "current-06/groceries",
                "current-07/salary",
            )
        )
        assert Counter(savings) == Counter(example_allocations("savings-02/interest"))
