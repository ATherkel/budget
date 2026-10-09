# Copyright 2026 Therkel
"""The Gold build: one publication's records from Silver and the household inputs."""

from collections.abc import Mapping, Sequence

from budget.gold.models import GoldAccount, GoldCategory, GoldPublication
from budget.gold.result import GoldRecords, GoldResult
from budget.gold.snapshots import monthly_balances
from budget.gold.transactions import gold_transactions
from budget.inputs.accounts import Account
from budget.silver.models import AccountEvidence, SilverResult


def build(
    *,
    silver: SilverResult,
    accounts: Mapping[str, Account],
    categories: Sequence[GoldCategory],
    publication: GoldPublication,
) -> GoldResult:
    """Derive Gold from a Silver result, the account registry and the taxonomy."""
    gold_accounts = tuple(
        _account(account, silver.account_evidence) for account in accounts.values()
    )
    transactions = gold_transactions(silver.transactions)
    records = GoldRecords(
        accounts=gold_accounts,
        categories=categories,
        transactions=transactions,
        monthly_balances=monthly_balances(
            gold_accounts, transactions, silver.account_evidence
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
