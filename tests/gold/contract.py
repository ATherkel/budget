# Copyright 2026 Therkel
"""Contract tests every `GoldRepository` implementation passes unchanged.

An implementation's test module subclasses `GoldRepositoryContract` and
provides a `repository` fixture holding the worked example
(`tests/gold/worked_example.py`). The contract fixes no order for returned
records, so the tests compare them as multisets.
"""

from collections import Counter
from datetime import date
from decimal import Decimal

from budget.gold import GoldRepository, ReportingMonth
from tests.gold.worked_example import (
    ACCOUNTS,
    CATEGORIES,
    CURRENT,
    PUBLICATION,
    SAVINGS,
    example_allocations,
    example_balances,
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

    def test_monthly_balances_are_filtered_by_an_inclusive_month_range(
        self, repository: GoldRepository
    ) -> None:
        february_to_april = repository.monthly_balances(
            start_month=ReportingMonth(2026, 2), end_month=ReportingMonth(2026, 4)
        )
        current_from_april = repository.monthly_balances(
            start_month=ReportingMonth(2026, 4),
            end_month=ReportingMonth(2026, 6),
            account_ids=[CURRENT],
        )

        assert Counter(february_to_april) == Counter(
            example_balances(CURRENT, 2, 3, 4) + example_balances(SAVINGS, 2, 3, 4)
        )
        # The latest published month is May, so June has no row: no data, not zero.
        assert Counter(current_from_april) == Counter(example_balances(CURRENT, 4, 5))

    def test_the_dimensions_are_the_whole_example(
        self, repository: GoldRepository
    ) -> None:
        assert Counter(repository.accounts()) == Counter(ACCOUNTS)
        assert Counter(repository.categories()) == Counter(CATEGORIES)

    def test_the_publication_is_the_one_the_records_belong_to(
        self, repository: GoldRepository
    ) -> None:
        assert repository.publication() == PUBLICATION

    def test_every_amount_and_balance_is_a_decimal(
        self, repository: GoldRepository
    ) -> None:
        start, end = date(2026, 1, 1), date(2026, 5, 31)
        transactions = repository.transactions(start_date=start, end_date=end)
        allocations = repository.category_allocations(start_date=start, end_date=end)
        snapshots = repository.monthly_balances(
            start_month=ReportingMonth.of(start), end_month=ReportingMonth.of(end)
        )
        money = [
            *(t.amount for t in transactions),
            *(t.balance_after for t in transactions),
            *(a.amount for a in allocations),
            *(s.opening_balance for s in snapshots),
            *(s.closing_balance for s in snapshots),
        ]

        # A float equals the Decimal of the same value, so the record comparisons
        # above would not notice one; only its type does.
        assert {type(value) for value in money if value is not None} == {Decimal}

    def test_an_empty_account_list_names_no_account(
        self, repository: GoldRepository
    ) -> None:
        start, end = date(2026, 1, 1), date(2026, 5, 31)

        found = {
            "transactions": list(
                repository.transactions(start_date=start, end_date=end, account_ids=[])
            ),
            "category_allocations": list(
                repository.category_allocations(
                    start_date=start, end_date=end, account_ids=[]
                )
            ),
            "monthly_balances": list(
                repository.monthly_balances(
                    start_month=ReportingMonth.of(start),
                    end_month=ReportingMonth.of(end),
                    account_ids=[],
                )
            ),
        }

        # Unlike None, which names every account.
        assert found == {
            "transactions": [],
            "category_allocations": [],
            "monthly_balances": [],
        }
