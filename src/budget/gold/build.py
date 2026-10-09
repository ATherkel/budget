# Copyright 2026 Therkel
"""The Gold build: one publication's records from Silver and the household inputs."""

from collections.abc import Mapping, Sequence

from budget.gold.models import GoldCategory, GoldPublication
from budget.gold.result import GoldRecords, GoldResult
from budget.inputs.accounts import Account
from budget.silver.models import SilverResult


def build(
    *,
    silver: SilverResult,
    accounts: Mapping[str, Account],
    categories: Sequence[GoldCategory],
    publication: GoldPublication,
) -> GoldResult:
    """Derive Gold from a Silver result, the account registry and the taxonomy."""
    del silver, accounts, categories
    return GoldResult(publication, GoldRecords())
