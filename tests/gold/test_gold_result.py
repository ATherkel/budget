# Copyright 2026 Therkel
"""`GoldResult`, the in-memory `GoldRepository` analytics tests build (#167)."""

from datetime import date

import pytest

from budget.gold import GoldRecords, GoldRepository, GoldResult
from tests.gold.contract import GoldRepositoryContract
from tests.gold.worked_example import PUBLICATION, RECORDS, example_transactions


class TestGoldResult(GoldRepositoryContract):
    @pytest.fixture
    def repository(self) -> GoldRepository:
        return GoldResult(PUBLICATION, RECORDS)


def test_changing_the_given_records_afterwards_does_not_change_the_result() -> None:
    given = example_transactions("current-04", "current-05")
    result = GoldResult(PUBLICATION, GoldRecords(transactions=given))

    given.clear()

    assert result.transactions(
        start_date=date(2026, 2, 1), end_date=date(2026, 2, 28)
    ) == tuple(example_transactions("current-04", "current-05"))
