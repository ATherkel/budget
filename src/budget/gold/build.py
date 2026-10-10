# Copyright 2026 Therkel
"""The Gold build: one publication's records from Silver and the household inputs."""

from collections.abc import Sequence

from budget.gold.models import GoldAccount, GoldCategory, GoldPublication
from budget.gold.result import GoldRecords, GoldResult
from budget.gold.snapshots import monthly_balances
from budget.gold.transactions import gold_transactions
from budget.inputs.accounts import Account
from budget.inputs.snapshot import ConfigurationSnapshot
from budget.inputs.taxonomy import Taxonomy
from budget.silver.models import AccountEvidence, SilverResult


def build(
    *,
    silver: SilverResult,
    configuration: ConfigurationSnapshot,
    publication: GoldPublication,
) -> GoldResult:
    """Derive Gold from a Silver result and the household's configuration.

    Nothing is classified yet: every transaction is `unknown`, and no category
    allocation, lineage or review item is published. The result is bound to
    `publication`, which the caller supplies.
    """
    gold_accounts = tuple(
        _account(account, silver.account_evidence)
        for account in configuration.accounts.values()
    )
    transactions = gold_transactions(silver.transactions)
    records = GoldRecords(
        accounts=gold_accounts,
        categories=_categories(configuration.taxonomy),
        transactions=transactions,
        monthly_balances=monthly_balances(
            gold_accounts,
            transactions,
            silver.account_evidence,
            silver.evidence_exports,
        ),
    )
    return GoldResult(publication, records)


def _account(account: Account, ranges: Sequence[AccountEvidence]) -> GoldAccount:
    """Publish a registry account, spanning its evidence ranges."""
    own = [r for r in ranges if r.account_id == account.account_id]
    return GoldAccount(
        account_id=account.account_id,
        display_name=account.display_name,
        account_type=account.account_type,
        ownership_scope=account.ownership_scope,
        currency=account.currency,
        closed_on=account.closed_on,
        coverage_start=min((r.covers_from for r in own), default=None),
        evidence_through=max((r.covers_through for r in own), default=None),
    )


def _categories(taxonomy: Taxonomy) -> tuple[GoldCategory, ...]:
    """Publish each category with its group flattened onto it."""
    return tuple(
        GoldCategory(
            category_id=category.category_id,
            name=category.name,
            group_id=category.group_id,
            group_name=taxonomy.groups[category.group_id].name,
            direction=taxonomy.groups[category.group_id].direction,
        )
        for category in taxonomy.categories.values()
    )
