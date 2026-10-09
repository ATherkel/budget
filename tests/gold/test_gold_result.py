# Copyright 2026 Therkel
"""`GoldResult`, the in-memory `GoldRepository` analytics tests build (#167)."""

import pytest

from budget.gold import GoldRepository, GoldResult
from tests.gold.contract import GoldRepositoryContract
from tests.gold.worked_example import PUBLICATION, RECORDS


class TestGoldResult(GoldRepositoryContract):
    @pytest.fixture
    def repository(self) -> GoldRepository:
        return GoldResult(PUBLICATION, RECORDS)
